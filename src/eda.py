"""Chapter 06 EDA. 공식 예제의 흐름에 동일 모집단과 병합 검증을 추가했다."""
from __future__ import annotations
from pathlib import Path
import pandas as pd

AS_OF = pd.Timestamp('2026-10-08 23:59:59')
PROCESSED_FILENAMES = {n: f'{n}_clean.csv' for n in ('customers', 'products', 'orders', 'order_items')}

def load_processed_sales_data(data_dir='data/processed'):
    data = {n: pd.read_csv(Path(data_dir) / f) for n, f in PROCESSED_FILENAMES.items()}
    data['order_items'].attrs['raw_snapshot_path'] = str(Path(data_dir).parent / 'raw' / 'order_items.csv')
    return data

def prepare_eda_data(data):
    d = {n: df.copy() for n, df in data.items()}
    for name, column in [('customers', 'signup_date'), ('orders', 'order_date')]:
        d[name][column] = pd.to_datetime(d[name][column], errors='coerce')
    d['orders']['order_month'] = d['orders']['order_date'].dt.strftime('%Y-%m')
    calc = d['order_items']['quantity'] * d['order_items']['unit_price']
    if 'line_total' in d['order_items']:
        assert d['order_items']['line_total'].equals(calc), '저장된 line_total 불일치'
    d['order_items']['line_total'] = calc
    for name, key in [('customers', 'customer_id'), ('products', 'product_id'), ('orders', 'order_id'), ('order_items', 'order_item_id')]:
        assert d[name][key].notna().all() and not d[name][key].duplicated().any(), f'{name} PK 실패'
    return d

def make_eda_questions(start, end):
    scope = f'{start}~{end} 양 끝 포함, completed, 유효 주문일≤2026-10-08; 금액=quantity×unit_price'
    return pd.DataFrame([
        ['카테고리별 금액 차이는 수량과 거래 단가에서 어떻게 나타나는가?', scope, 'orders, order_items, products', '금액·수량·수량가중 거래단가', 'groupby sum; 금액/수량', '카테고리 합계=집계 전 clean completed 합계'],
        ['월별 주문 수와 평균 주문금액은 어떻게 달라지는가?', scope, 'orders, order_items', '월 금액·고유 주문 수·주문당 금액', 'order_id별 합산 후 월별 집계', '월 합계=집계 전 clean; 두 집계 방식 일치'],
        ['도시별 고객 수와 완료 주문금액 순위는 같은가?', scope+'; 고객수는 clean 고객 전체', 'customers, orders, order_items', '도시 고객수·구매고객수·금액·고객당 금액', 'customer_id→city many_to_one', '도시 합계=집계 전 clean; 고객수 합계=clean 고객수'],
        ['결제수단별 평균 주문금액은 어떻게 다른가?', scope, 'orders, order_items', '결제수단별 주문금액 평균·주문 수', '라인→주문 합산→결제수단별 mean', '주문금액 총합=집계 전 clean; 라인평균과 구분'],
        ['반복 구매 고객과 고액 1회 고객은 몇 명인가?', scope, 'customers, orders, order_items', '고유 주문수·총금액·평균 주문금액', '고객별 nunique; 반복≥2; 고액1회≥전체 주문금액75%분위', '고객 합계=집계 전 clean; 분류 기준·기간 고정'],
    ], columns=['질문', '분석 범위', '필요 데이터', '지표', '계산 방법', '검증 방법'])

def _frequency(df, column, count_name):
    out = df[column].value_counts(dropna=False).rename_axis(column).reset_index(name=count_name)
    out['ratio_pct'] = (out[count_name] / len(df) * 100).round(2)
    return out

def run_basic_eda(data):
    d = prepare_eda_data(data)
    c, p, o, i = [d[n] for n in PROCESSED_FILENAMES]
    checks = []
    for child, parent, key in [(o,c,'customer_id'), (i,o,'order_id'), (i,p,'product_id')]:
        missing = int((~child[key].isin(parent[key])).sum())
        checks.append([f'FK {key}', missing, 0, missing == 0])
        assert missing == 0, f'FK 실패: {key}'
    base = i.merge(o[['order_id','customer_id','order_date','order_status','payment_method','order_month']], on='order_id', how='left', validate='many_to_one', indicator=True)
    assert len(base) == len(i) and base['_merge'].eq('both').all()
    checks.append(['orders 병합 행 증가', len(base)-len(i), 0, len(base)==len(i)])
    base = base.drop(columns='_merge')
    complete = base['order_status'].eq('completed')
    valid = base['order_date'].notna()
    past = base['order_date'].le(AS_OF)
    selected = complete & valid & past
    masks = [('전체 clean 상세 (매출 아님)', pd.Series(True,index=base.index)), ('completed 전체',complete), ('completed 날짜 결측 제외',complete & ~valid), ('completed 미래 후보 제외',complete & valid & ~past), ('최종 분석 모집단',selected)]
    scope = pd.DataFrame([[label,int(mask.sum()),int(base.loc[mask,'order_id'].nunique()),int(base.loc[mask,'line_total'].sum())] for label,mask in masks],columns=['범위','상세행수','주문수','금액합계'])
    sales = base.loc[selected].copy()
    before = len(sales)
    sales = sales.merge(p[['product_id','category','price']],on='product_id',how='left',validate='many_to_one',indicator=True)
    assert len(sales)==before and sales['_merge'].eq('both').all() and sales['category'].notna().all()
    checks.append(['products 병합 행 증가',len(sales)-before,0,len(sales)==before])
    sales = sales.drop(columns='_merge')
    before = len(sales)
    sales = sales.merge(c[['customer_id','city']],on='customer_id',how='left',validate='many_to_one',indicator=True)
    assert len(sales)==before and sales['_merge'].eq('both').all() and sales['city'].notna().all()
    checks.append(['customers 병합 행 증가',len(sales)-before,0,len(sales)==before])
    sales = sales.drop(columns='_merge')
    assert len(sales)>0
    start, end = sales['order_date'].min().date().isoformat(), sales['order_date'].max().date().isoformat()
    eligible_ids = o.loc[o['order_status'].eq('completed') & o['order_date'].notna() & o['order_date'].le(AS_OF), 'order_id']
    independent_items = i.loc[i['order_id'].isin(eligible_ids)]
    total = int((independent_items['quantity'] * independent_items['unit_price']).sum())
    category = sales.groupby('category',as_index=False).agg(total_quantity=('quantity','sum'),total_sales=('line_total','sum'),order_count=('order_id','nunique'),sold_product_count=('product_id','nunique')).sort_values('total_sales',ascending=False)
    category['sales_ratio_pct'] = (category['total_sales']/total*100).round(2)
    category['quantity_weighted_unit_price'] = category['total_sales']/category['total_quantity']
    order_amounts = sales.groupby(['order_id','customer_id','order_date','order_month','payment_method','city'],as_index=False).agg(order_total=('line_total','sum'),item_rows=('order_item_id','count'))
    eligible_order_ids = o.loc[o['order_status'].eq('completed') & o['order_date'].notna() & o['order_date'].le(AS_OF),'order_id']
    no_items = int((~eligible_order_ids.isin(order_amounts['order_id'])).sum())
    scope['주석'] = ['', '', '금액분석의 공통 제외', '기준일 이후를 공통 제외', f'금액 상세가 없는 조건충족 주문 {no_items}건; 평균 분모 제외']
    monthly = order_amounts.groupby('order_month',as_index=False).agg(total_sales=('order_total','sum'),order_count=('order_id','nunique'),avg_order_value=('order_total','mean')).sort_values('order_month')
    monthly_check = sales.groupby('order_month',as_index=False).agg(total_sales=('line_total','sum'),order_count=('order_id','nunique')).sort_values('order_month')
    pd.testing.assert_frame_equal(monthly[['order_month','total_sales','order_count']].reset_index(drop=True),monthly_check.reset_index(drop=True))
    # raw 고유 상세와 비교해 일부 상세가 격리된 주문의 영향을 드러낸다.
    raw_path = i.attrs.get('raw_snapshot_path')
    assert raw_path and Path(raw_path).is_file(), '부분 보존 주문 감사를 위한 원본 snapshot 필요'
    raw_items = pd.read_csv(raw_path).drop_duplicates()
    raw_counts = raw_items.groupby('order_id')['order_item_id'].nunique().rename('raw_unique_item_count')
    clean_counts = i.groupby('order_id')['order_item_id'].nunique().rename('clean_item_count')
    partial_audit = pd.concat([raw_counts, clean_counts], axis=1).fillna(0).reset_index()
    partial_audit['excluded_item_count'] = partial_audit.raw_unique_item_count-partial_audit.clean_item_count
    partial_audit['partially_retained'] = partial_audit.clean_item_count.gt(0) & partial_audit.excluded_item_count.gt(0)
    partial_ids = partial_audit.loc[partial_audit.partially_retained,'order_id']
    partial_audit['in_analysis'] = partial_audit.order_id.isin(order_amounts.order_id)
    selected_partial = partial_audit.loc[partial_audit.partially_retained & partial_audit.in_analysis].copy()
    order_amounts['partially_retained'] = order_amounts.order_id.isin(partial_ids)
    partial_audit = partial_audit.loc[partial_audit.partially_retained].copy()
    sensitivity_rows = []
    for label, subset in [('남은 유효 상세 포함 (기본)',sales),('일부 상세 제외 주문 전부 제외',sales.loc[~sales.order_id.isin(partial_ids)])]:
        order_totals = subset.groupby('order_id')['line_total'].sum()
        sensitivity_rows.append([label,len(subset),len(order_totals),int(order_totals.sum()),float(order_totals.mean())])
    sensitivity = pd.DataFrame(sensitivity_rows,columns=['분석 범위','상세행수','주문수','금액합계','남은상세 주문금액평균'])
    customer = order_amounts.groupby(['customer_id','city'],as_index=False).agg(order_count=('order_id','nunique'),total_sales=('order_total','sum'),avg_order_value=('order_total','mean')).sort_values('total_sales',ascending=False)
    threshold = float(order_amounts['order_total'].quantile(.75))
    customer['customer_group'] = '기타 1회 구매'
    customer.loc[customer['order_count'].ge(2),'customer_group'] = '반복 구매 (2회 이상)'
    customer.loc[customer['order_count'].eq(1) & customer['avg_order_value'].ge(threshold),'customer_group'] = '고액 1회 구매 (주문금액 Q75 이상)'
    customer_city = _frequency(c,'city','customer_count')
    city_sales = customer_city.merge(order_amounts.groupby('city',as_index=False).agg(total_sales=('order_total','sum'),order_count=('order_id','nunique'),buyer_count=('customer_id','nunique')),on='city',how='left',validate='one_to_one').fillna({'total_sales':0,'order_count':0,'buyer_count':0})
    city_sales['sales_per_registered_customer'] = city_sales['total_sales']/city_sales['customer_count']
    city_sales['customer_rank'] = city_sales['customer_count'].rank(method='min',ascending=False).astype(int)
    city_sales['sales_rank'] = city_sales['total_sales'].rank(method='min',ascending=False).astype(int)
    city_sales = city_sales.sort_values('total_sales',ascending=False)
    product_category = _frequency(p,'category','product_count')
    category_comparison = product_category.merge(category,on='category',how='left',validate='one_to_one').fillna(0)
    category_comparison['product_rank'] = category_comparison['product_count'].rank(method='min',ascending=False).astype(int)
    category_comparison['sales_rank'] = category_comparison['total_sales'].rank(method='min',ascending=False).astype(int)
    category_comparison = category_comparison.sort_values('total_sales',ascending=False)
    payment_order = order_amounts.groupby('payment_method',as_index=False).agg(order_count=('order_id','nunique'),total_sales=('order_total','sum'),avg_order_value=('order_total','mean'),median_order_value=('order_total','median')).sort_values('avg_order_value',ascending=False)
    line_mean = sales.groupby('payment_method',as_index=False).agg(line_count=('order_item_id','count'),mean_line_total=('line_total','mean'))
    payment_order = payment_order.merge(line_mean,on='payment_method',validate='one_to_one')
    month_category = sales.groupby(['order_month','category'],as_index=False).agg(total_sales=('line_total','sum'),total_quantity=('quantity','sum'),order_count=('order_id','nunique'))
    groups = customer.groupby('customer_group',as_index=False).agg(customer_count=('customer_id','count'),order_count=('order_count','sum'),total_sales=('total_sales','sum'),mean_customer_sales=('total_sales','mean')).sort_values('total_sales',ascending=False)
    totals = [('집계 전 clean 독립 계산',total),('병합 상세',int(sales['line_total'].sum())),('카테고리',int(category['total_sales'].sum())),('월',int(monthly['total_sales'].sum())),('도시',int(city_sales['total_sales'].sum())),('결제수단',int(payment_order['total_sales'].sum())),('고객',int(customer['total_sales'].sum())),('월×카테고리',int(month_category['total_sales'].sum()))]
    for label,value in totals:
        checks.append([label+' 합계',value,total,value==total])
        assert value==total
    checks.append(['도시 고객수 합계',int(customer_city['customer_count'].sum()),len(c),int(customer_city['customer_count'].sum())==len(c)])
    checks.append(['결제수단 주문수',int(payment_order['order_count'].sum()),len(order_amounts),int(payment_order['order_count'].sum())==len(order_amounts)])
    category_price = p.groupby('category',as_index=False).agg(product_count=('product_id','count'),avg_price=('price','mean'),min_price=('price','min'),max_price=('price','max'))
    # 상품 목록의 극단 가격은 거래가격과 분리해서 진단한다.
    price_candidates = p.loc[p['price_outlier_candidate'].fillna(False).astype(bool)] if 'price_outlier_candidate' in p else p.loc[p['price']>1_000_000]
    candidate_sales = sales.loc[sales['product_id'].isin(price_candidates['product_id'])]
    price_check = pd.DataFrame([['상품 목록 가격 후보',len(price_candidates),int(price_candidates['price'].max()) if len(price_candidates) else 0],['해당 상품의 completed 상세',len(candidate_sales),int(candidate_sales['unit_price'].max()) if len(candidate_sales) else 0]],columns=['확인','건수','최댓값'])
    result_summary = pd.DataFrame([
        ['도시 고객수와 금액 차이','city_sales','구매 고객 비중·주문 수·고객당 금액을 함께 비교'],
        ['상품 수와 거래금액 차이','category_comparison','판매 수량과 수량가중 거래단가를 함께 비교'],
        ['월별 차이','monthly_sales, month_category','경계 월을 제외하고 주문수와 객단가를 분리'],
        ['고액 고객의 반복성','customer_groups','기간 내 2회 이상과 고액 1회를 분리; 미래 재구매는 미확인'],
    ],columns=['관찰 주제','결과표','다음 질문'])
    return dict(questions=make_eda_questions(start,end),customer_city=customer_city,customer_gender=_frequency(c,'gender','customer_count'),product_category=product_category,category_price=category_price,order_status=_frequency(o,'order_status','order_count'),payment_method=_frequency(o,'payment_method','order_count'),category_sales=category,monthly_sales=monthly,customer_sales=customer,eda_result_summary=result_summary,scope=scope,validation=pd.DataFrame(checks,columns=['검증','실제값','기대값','통과']),city_sales=city_sales,category_comparison=category_comparison,payment_order=payment_order,month_category=month_category,customer_groups=groups,price_check=price_check,partial_order_audit=partial_audit,partial_sensitivity=sensitivity,sales_base=sales,order_amounts=order_amounts,parameters=pd.DataFrame([['기준일','2026-10-08'],['기간 시작',start],['기간 종료',end],['고액 1회 기준(Q75 원)',str(threshold)],['상세 없는 조건충족 주문 수',str(no_items)],['전체 부분보존 주문 수',str(len(partial_audit))],['분석 내 부분보존 주문 수',str(len(selected_partial))]],columns=['항목','값']))

def save_eda_outputs(results,output_dir='reports',encoding='utf-8-sig'):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    saved=[]
    for name,df in results.items():
        if name in {'sales_base','order_amounts'}: continue
        path=out/f'ch06_{name}.csv'; df.to_csv(path,index=False,encoding=encoding); saved.append(path)
    return saved

def build_eda_report(results):
    def table(key): return '\n'.join(line.rstrip() for line in results[key].to_string(index=False).splitlines())
    return '\n\n'.join(['# Chapter 06 EDA 요약 보고서','작성·실행: 2026-10-08. 수업용 합성 데이터의 Chapter05 clean 4개를 사용했다. 금액은 completed, 유효한 주문일, 2026-10-08 이하인 동일 모집단의 quantity × unit_price다. 거래 수수료·할인·원가가 없어 회계상 순매출 또는 이익으로 부르지 않는다.','## 분석 범위\n```text\n'+table('parameters')+'\n```','## 질문·지표·검증\n```text\n'+table('questions')+'\n```','## 모집단과 제외 영향\n```text\n'+table('scope')+'\n```','## 카테고리\n```text\n'+table('category_sales')+'\n```','## 월별\n```text\n'+table('monthly_sales')+'\n```','## 고객 유형\n```text\n'+table('customer_groups')+'\n```','## 총합·병합 검증\n```text\n'+table('validation')+'\n```','## 다음 질문\n```text\n'+table('eda_result_summary')+'\n```','## 일부 상세 제외 주문의 영향\n```text\n'+table('partial_sensitivity')+'\n```','## 해석의 한계\n주문금액은 정제 후 남은 유효 상세의 합이다. 원래 주문의 청구총액이 아니다. 일부 상세가 격리된 주문은 기본 분석에 포함하되 위 민감도 표로 그 영향도 비교했다. 고객수·상품수는 clean 전체, 금액과 구매고객은 위 completed 모집단이므로 분모를 구분했다. 분석 기간을 실제 거래일의 최소·최대로 정해 경계 월은 보수적으로 제외했다. 데이터 추출 시작·종료일이 없어 경계 월 전체 수집 여부는 확인할 수 없다. 목록 가격 이상 후보와 거래 단가는 다르다. 고액 기준은 이 샘플의 Q75이며 고객 미래가치·광고효과·선호도는 단정하지 않았다. 자세한 관찰·가설·추가 검증과 LLM 판단은 chapter06/chapter06.ipynb에 있다.'])+'\n'
