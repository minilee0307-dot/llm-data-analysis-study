"""Chapter07: 공식 시각화 흐름에 동일 모집단·artist 검증을 추가한 함수들."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import dates as mdates, font_manager
from matplotlib.ticker import FuncFormatter, MaxNLocator
from src.eda import AS_OF, load_processed_sales_data, prepare_eda_data, run_basic_eda

FIGURE_FILENAMES = {'category_sales':'graph01.png','monthly_sales':'graph02.png',
    'product_price':'graph03.png','price_quantity':'graph04.png',
    'top_customers':'graph05.png','order_status':'graph06.png','bins_comparison':'graph07.png'}
MONEY=FuncFormatter(lambda x,pos:f'{x:,.0f}')
ZOOM_MAX=200_000

@dataclass
class ChartResult:
    path: Path
    validation: pd.DataFrame


def setup_korean_font(font_family=None):
    candidates=[font_family] if font_family else []
    candidates+=['AppleGothic','NanumGothic','Nanum Gothic','Malgun Gothic','Noto Sans CJK KR']
    installed={f.name:f.fname for f in font_manager.fontManager.ttflist}
    selected=next((f for f in candidates if f in installed and Path(installed[f]).is_file()),None)
    if selected is None:
        raise RuntimeError('사용 가능한 한글 폰트를 설치한 뒤 다시 실행하세요.')
    plt.rcParams.update({'font.family':selected,'axes.unicode_minus':False,
        'font.size':11,'axes.titlesize':14,'axes.labelsize':11,'figure.facecolor':'white',
        'savefig.facecolor':'white','axes.spines.top':False,'axes.spines.right':False})
    return {'font_family':selected,'font_path':installed[selected]}


def prepare_visualization_data(processed_dir='data/processed'):
    original=load_processed_sales_data(processed_dir)
    data=prepare_eda_data(original)
    eda=run_basic_eda(original)
    products=data['products']; sales=eda['sales_base']
    for df,key in [(products,'price'),(data['order_items'],'quantity'),(data['order_items'],'unit_price')]:
        assert pd.api.types.is_numeric_dtype(df[key]) and df[key].notna().all()
    category=eda['category_sales'].rename(columns={'total_sales':'completed_amount','sales_ratio_pct':'amount_ratio_pct'})
    monthly=eda['monthly_sales'].rename(columns={'total_sales':'completed_amount','order_count':'completed_order_count','avg_order_value':'average_completed_order_amount'}).copy()
    # 달이 빠지면 Unknown(NaN)으로 남긴다. 관측 금액 0과 달력상 누락은 다르다.
    calendar=pd.period_range(monthly.order_month.min(),monthly.order_month.max(),freq='M').astype(str)
    observed_months=set(monthly.order_month)
    monthly=monthly.set_index('order_month').reindex(calendar).rename_axis('order_month').reset_index()
    monthly['month_start']=pd.to_datetime(monthly.order_month+'-01')
    monthly['observed_in_selected_data']=monthly.order_month.isin(observed_months)
    monthly['zero_amount_observed']=monthly.observed_in_selected_data & monthly.completed_amount.eq(0)
    product_sales=sales.groupby(['product_id','category','price'],as_index=False).agg(completed_quantity=('quantity','sum'),completed_amount=('line_total','sum')).sort_values('completed_amount',ascending=False)
    customer=eda['customer_sales'].rename(columns={'order_count':'completed_order_count','total_sales':'completed_amount','avg_order_value':'average_completed_order_amount'}).copy()
    # 원본 ID를 출력하지 않는 순위 기반 라벨. 재실행 시 같은 순서가 되도록 동률 ID 정렬.
    customer=customer.sort_values(['completed_amount','customer_id'],ascending=[False,True]).reset_index(drop=True)
    customer['customer_label']=[f'구매금액 순위 {i:02d}' for i in range(1,len(customer)+1)]
    anonymous_customer=customer[['customer_label','completed_order_count','completed_amount','average_completed_order_amount','customer_group']].copy()
    status=eda['order_status'][['order_status','order_count','ratio_pct']].copy()
    checks=eda['validation'].rename(columns={'검증':'check','실제값':'actual','기대값':'expected','통과':'passed'})
    total=int(sales.line_total.sum())
    extra=[]
    for name, actual,expected in [('상품 금액 합계',int(product_sales.completed_amount.sum()),total),('달력 재색인 금액 합계',int(monthly.completed_amount.sum()),total),('전체 상태 건수',int(status.order_count.sum()),len(data['orders'])),('히스토그램 전체 표본',int(products.price.notna().sum()),len(products))]:
        extra.append({'check':name,'actual':actual,'expected':expected,'passed':actual==expected})
    checks=pd.concat([checks,pd.DataFrame(extra)],ignore_index=True)
    assert checks.passed.all()
    prices=products.price.to_numpy()
    histogram_rows=[]
    for sample_label,values in [('전체 상품',prices),('0~200000원 확대',prices[(prices>=0)&(prices<=ZOOM_MAX)])]:
        for bins in [10,20,30]:
            counts,edges=np.histogram(values,bins=bins)
            for j,count in enumerate(counts):
                histogram_rows.append([sample_label,bins,j,edges[j],edges[j+1],int(count)])
    histogram_table=pd.DataFrame(histogram_rows,columns=['표본','bins','구간','하한(포함)','상한(마지막구간만 포함)','상품수'])
    parameters=dict(eda['parameters'].values)
    return {**data,'eda_results':eda,'category_sales':category,'monthly_sales':monthly,
        'product_sales':product_sales,'customer_sales':anonymous_customer,'order_status':status,
        'completed_order_sales':sales,'visualization_validation':checks,
        'histogram_table':histogram_table,'parameters':parameters,
        'date_range':f"{parameters['기간 시작']}~{parameters['기간 종료']}",
        'source_files':pd.DataFrame([{'파일':f'{name}_clean.csv','행':len(df),'열':df.shape[1]} for name,df in original.items()])}


def _scope_title(ax,title,data_range=None,note=None):
    ax.set_title(title,loc='left',pad=42,fontweight='normal')
    subtitle=(f'{data_range} | completed · 유효 주문일 · 기준일 2026-10-08' if data_range else '')
    if note: subtitle=(subtitle+'\n' if subtitle else '')+note
    if subtitle: ax.text(0,1.01,subtitle,transform=ax.transAxes,fontsize=8.3,va='bottom',color='#555555')


def _finish(fig,path,checks,show):
    result=pd.DataFrame(checks,columns=['그래프 검증','실제값','기대값','통과'])
    assert result['통과'].all(),result.to_string(index=False)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fig.tight_layout(pad=2.0)
    fig.savefig(path,dpi=150,bbox_inches='tight',metadata={'Software':'matplotlib / Chapter07 reproducible output'})
    if show:
        print('artist↔집계표 교차 검증:',len(result),'/',len(result),'PASS')
        plt.show()
    plt.close(fig)
    return ChartResult(path,result)


def plot_category_sales(category_sales,output_path,show=True,data_range=None):
    table=category_sales.sort_values('completed_amount',ascending=False).reset_index(drop=True)
    fig,ax=plt.subplots(figsize=(10.4,5.5))
    bars=ax.bar(table.category,table.completed_amount,color='#4177a6',width=.65)
    heights=np.array([p.get_height() for p in bars])
    np.testing.assert_array_equal(heights,table.completed_amount.to_numpy())
    assert [t.get_text() for t in ax.get_xticklabels()]==table.category.tolist()
    _scope_title(ax,'카테고리별 완료 주문 상세 금액',data_range)
    ax.set_xlabel('카테고리 (금액 내림차순)');ax.set_ylabel('남은 유효 상세 금액 합계 (원)');ax.set_ylim(0,float(table.completed_amount.max())*1.20)
    ax.yaxis.set_major_formatter(MONEY);ax.grid(axis='y',alpha=.20);ax.set_axisbelow(True)
    for bar,value in zip(bars,table.completed_amount):ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+table.completed_amount.max()*.02,f'{value/1_000_000:.2f}백만',ha='center',fontsize=9)
    checks=[['bar heights',int(heights.sum()),int(table.completed_amount.sum()),True],['범주 순서',len(bars),len(table),True],['값 축 시작',ax.get_ylim()[0],0,ax.get_ylim()[0]==0]]
    return _finish(fig,output_path,checks,show)


def plot_monthly_sales(monthly_sales,output_path,show=True,data_range=None):
    t=monthly_sales.sort_values('month_start').reset_index(drop=True)
    fig,ax=plt.subplots(figsize=(11.4,5.5))
    line,=ax.plot(t.month_start,t.completed_amount,marker='o',markersize=5,color='#4177a6',linewidth=2,label='월별 금액 (누락 월은 단절)')
    np.testing.assert_allclose(line.get_ydata(),t.completed_amount.to_numpy(dtype=float),equal_nan=True)
    np.testing.assert_allclose(line.get_xdata(orig=False),mdates.date2num(t.month_start.to_numpy()))
    assert t.month_start.is_monotonic_increasing
    _scope_title(ax,'월별 완료 주문 상세 금액',data_range,note='양 끝 월의 수집 완전성은 확인되지 않음 · 추출 기간 정보 없음')
    ax.set_xlabel('주문 월');ax.set_ylabel('남은 유효 상세 금액 합계 (원)');ax.set_ylim(bottom=0)
    ax.set_xticks(t.month_start);ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'));plt.setp(ax.get_xticklabels(),rotation=45,ha='right',fontsize=9)
    ax.yaxis.set_major_formatter(MONEY);ax.grid(axis='y',alpha=.20);ax.legend(loc='upper left',fontsize=8)
    for date,y in zip(t.month_start,t.completed_amount):
        if pd.notna(y):ax.annotate(f'{y/1_000_000:.2f}백만',(date,y),xytext=(0,7),textcoords='offset points',ha='center',fontsize=8)
    checks=[['line y',float(np.nansum(line.get_ydata())),float(t.completed_amount.sum()),True],['line x 달력',len(line.get_xdata()),len(t),True],['시간 정렬',int(t.month_start.is_monotonic_increasing),1,True],['누락 월을 0으로 채우지 않음',int(np.isnan(line.get_ydata()).sum()),int(t.completed_amount.isna().sum()),True]]
    return _finish(fig,output_path,checks,show)


def _hist_check(ax,values,bins,label):
    n,edges,patches=ax.hist(values,bins=bins,color='#4177a6',edgecolor='white',linewidth=.8)
    expected,expected_edges=np.histogram(values,bins=bins)
    np.testing.assert_array_equal(n,expected);np.testing.assert_allclose(edges,expected_edges)
    np.testing.assert_array_equal([p.get_height() for p in patches],expected)
    return [f'{label} hist counts',int(n.sum()),len(values),int(n.sum())==len(values)]


def plot_product_price_hist(products,output_path,show=True,bins=20):
    prices=products.price.to_numpy();normal=prices[(prices>=0)&(prices<=ZOOM_MAX)];outside=prices[(prices<0)|(prices>ZOOM_MAX)]
    assert len(prices)==len(normal)+len(outside)
    fig,axes=plt.subplots(1,2,figsize=(11.8,5.5))
    checks=[_hist_check(axes[0],prices,bins,'전체'),_hist_check(axes[1],normal,bins,'확대')]
    for ax in axes:ax.set_xlabel('상품 목록 가격 (원)');ax.set_ylabel('상품 수 (개)');ax.set_xlim(left=0);ax.set_ylim(bottom=0);ax.xaxis.set_major_formatter(MONEY);ax.yaxis.set_major_locator(MaxNLocator(integer=True));ax.grid(axis='y',alpha=.15);ax.tick_params(axis='x',rotation=25,labelsize=9)
    axes[0].set_title(f'전체 {len(prices)}개 · bins={bins}',loc='left',fontweight='normal');axes[1].set_title(f'0~200,000원 확대 · {len(normal)}개',loc='left',fontweight='normal')
    axes[1].set_xlim(0,ZOOM_MAX)
    fig.suptitle('상품 목록 가격 분포 — 전체와 확대 범위',fontsize=15,fontweight='normal',y=1.04)
    fig.text(.5,-.025,f'주문 상태와 무관한 clean 상품 {len(prices)}개 | 확대 범위 밖 {len(outside)}개, 최대 {prices.max():,.0f}원 | 극단 후보를 삭제하지 않음',ha='center',fontsize=9)
    checks.append(['전체=확대+밖',len(prices),len(normal)+len(outside),True])
    return _finish(fig,output_path,checks,show)


def plot_price_quantity_scatter(product_sales,output_path,show=True,data_range=None):
    table=product_sales.reset_index(drop=True);normal=table.loc[table.price.le(ZOOM_MAX)].copy()
    fig,axes=plt.subplots(1,2,figsize=(11.8,5.3));checks=[]
    for ax,t,label in [(axes[0],table,'전체'),(axes[1],normal,'0~200,000원 확대')]:
        points=ax.scatter(t.price,t.completed_quantity,alpha=.72,color='#4177a6',s=38)
        offsets=np.asarray(points.get_offsets())
        np.testing.assert_allclose(offsets,t[['price','completed_quantity']].to_numpy())
        checks.append([f'{label} scatter xy',len(offsets),len(t),True])
        ax.set_title(f'{label} · 판매 상품 {len(t)}개',loc='left',fontweight='normal');ax.set_xlabel('현재 상품 목록 가격 (원)');ax.set_ylabel('완료 주문 판매 수량 (개)');ax.set_xlim(left=0);ax.set_ylim(bottom=0);ax.xaxis.set_major_formatter(MONEY);ax.tick_params(axis='x',rotation=25,labelsize=9);ax.grid(alpha=.15)
    axes[1].set_xlim(0,ZOOM_MAX)
    fig.suptitle('상품 목록 가격과 완료 주문 판매 수량',fontweight='normal',fontsize=15,y=1.04)
    fig.text(.5,-.025,f'{data_range} | completed · 유효 주문일 · 기준일 2026-10-08 | 한 점=판매 상품 1개 · 목록 가격은 거래 단가와 다름',ha='center',fontsize=8.5)
    return _finish(fig,output_path,checks,show)


def plot_top_customers(customer_sales,output_path,show=True,top_n=10,data_range=None):
    top=customer_sales.head(top_n).sort_values('completed_amount').copy()
    fig,ax=plt.subplots(figsize=(10.4,6.0));bars=ax.barh(top.customer_label,top.completed_amount,color='#4177a6')
    np.testing.assert_array_equal([b.get_width() for b in bars],top.completed_amount.to_numpy())
    assert [x.get_text() for x in ax.get_yticklabels()]==top.customer_label.tolist()
    _scope_title(ax,f'완료 주문 상세 금액 상위 {len(top)}명',data_range,note='순위 기반 익명 라벨 · 전체 고객 분포가 아님')
    ax.set_xlabel('남은 유효 상세 금액 합계 (원)');ax.set_ylabel('구매금액 순위 (익명)');ax.set_xlim(0,float(top.completed_amount.max())*1.2);ax.xaxis.set_major_formatter(MONEY);ax.grid(axis='x',alpha=.20);ax.set_axisbelow(True)
    for bar,v in zip(bars,top.completed_amount):ax.text(v+top.completed_amount.max()*.015,bar.get_y()+bar.get_height()/2,f'{v:,.0f}',va='center',fontsize=9)
    return _finish(fig,output_path,[['barh widths',int(top.completed_amount.sum()),int(sum(b.get_width() for b in bars)),True],['익명 라벨 수',len(bars),len(top),True],['값 축 시작',ax.get_xlim()[0],0,ax.get_xlim()[0]==0]],show)


def plot_order_status(order_status,output_path,show=True):
    fig,ax=plt.subplots(figsize=(9.4,5.0));bars=ax.bar(order_status.order_status,order_status.order_count,color='#4177a6',width=.55)
    np.testing.assert_array_equal([b.get_height() for b in bars],order_status.order_count.to_numpy())
    _scope_title(ax,'전체 clean 주문의 상태별 건수',note=f'전체 {int(order_status.order_count.sum())}건 · 날짜/상태 필터 전 주문 마스터')
    ax.set_xlabel('주문 상태');ax.set_ylabel('주문 수 (건)');ax.set_ylim(0,float(order_status.order_count.max())*1.2);ax.yaxis.set_major_locator(MaxNLocator(integer=True));ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    for b,n in zip(bars,order_status.order_count):ax.text(b.get_x()+b.get_width()/2,n+2,str(n),ha='center')
    return _finish(fig,output_path,[['status bar heights',int(sum(b.get_height() for b in bars)),int(order_status.order_count.sum()),True],['값 축 시작',ax.get_ylim()[0],0,ax.get_ylim()[0]==0]],show)


def plot_bins_comparison(products,output_path,show=True):
    prices=products.price.to_numpy();normal=prices[(prices>=0)&(prices<=ZOOM_MAX)]
    fig,axes=plt.subplots(2,3,figsize=(13,8));checks=[]
    for row,(values,label) in enumerate([(prices,f'전체 {len(prices)}개'),(normal,f'확대 {len(normal)}개 · 범위 밖 {len(prices)-len(normal)}개')]):
        for col,bins in enumerate([10,20,30]):
            ax=axes[row,col];checks.append(_hist_check(ax,values,bins,f'{label} bins={bins}'))
            ax.set_title(f'{label}\nbins={bins}',loc='left',fontsize=11);ax.set_xlabel('목록 가격 (원)');ax.set_ylabel('상품 수 (개)');ax.xaxis.set_major_formatter(MONEY);ax.tick_params(axis='x',rotation=25,labelsize=8);ax.set_xlim(left=0);ax.yaxis.set_major_locator(MaxNLocator(integer=True));ax.grid(axis='y',alpha=.15)
    fig.suptitle('같은 상품 표본의 bins=10·20·30 비교',fontsize=15,fontweight='normal',y=1.02)
    return _finish(fig,output_path,checks,show)


def create_all_figures(data,figure_dir,show=False):
    out=Path(figure_dir);checks=[];paths=[]
    calls=[('category_sales',plot_category_sales,data['category_sales'],{'data_range':data['date_range']}),('monthly_sales',plot_monthly_sales,data['monthly_sales'],{'data_range':data['date_range']}),('product_price',plot_product_price_hist,data['products'],{}),('price_quantity',plot_price_quantity_scatter,data['product_sales'],{'data_range':data['date_range']}),('top_customers',plot_top_customers,data['customer_sales'],{'data_range':data['date_range']}),('order_status',plot_order_status,data['order_status'],{}),('bins_comparison',plot_bins_comparison,data['products'],{})]
    for name,fn,table,kwargs in calls:
        result=fn(table,out/FIGURE_FILENAMES[name],show=show,**kwargs);paths.append(result.path)
        check=result.validation.copy();check.insert(0,'graph',name);checks.append(check)
    return paths,pd.concat(checks,ignore_index=True)


def create_visualization_summary(data):
    return pd.DataFrame([
        ['카테고리 금액 비교','막대','completed+유효과거날짜','0축·금액내림차순·원 단위','graph01.png'],
        ['월별 금액 변화','선','동일 completed 모집단','월순서·14개월달력·누락은NaN','graph02.png'],
        ['상품 목록 가격 분포','히스토그램','전체 clean 상품96개','전체96+확대95·범위밖1 공개','graph03.png'],
        ['목록 가격과 판매수량','산점도','동일 completed 판매상품','한점=상품·전체/확대범위 명시','graph04.png'],
        ['구매금액 상위고객','가로막대','동일 completed 구매고객 Top10','익명순위·반복/객단가와함께판단','graph05.png'],
        ['주문 상태별 건수','막대','전체 clean 주문298건','완료금액모집단과구분·0축','graph06.png'],
        ['bins별 모양 변화','히스토그램 비교','동일 전체96/확대95개','bins10/20/30·표본별합계검증','graph07.png'],
    ],columns=['질문','그래프','범위','오해 방지','이미지'])


def save_visualization_outputs(data,report_dir,artist_validation):
    out=Path(report_dir);out.mkdir(parents=True,exist_ok=True);saved=[]
    tables={key:data[key] for key in ['category_sales','monthly_sales','product_sales','customer_sales','order_status','histogram_table','visualization_validation']}
    tables['artist_validation']=artist_validation
    tables['scope']=data['eda_results']['scope'];tables['partial_sensitivity']=data['eda_results']['partial_sensitivity']
    for key,df in tables.items():
        p=out/f'ch07_{key}.csv';df.to_csv(p,index=False,encoding='utf-8-sig');saved.append(p)
    return saved


def build_visualization_report(summary,data,artist_validation):
    def tab(df):return '\n'.join(line.rstrip() for line in df.to_string(index=False).splitlines())
    total=int(data['completed_order_sales'].line_total.sum())
    return '\n\n'.join(['# Chapter 07 시각화 요약','작성·실행일: 2026-10-11. 분석 기준일은 Chapter06과 같은 2026-10-08로 고정했다.','## 분석 범위',f"{data['date_range']} 양 끝 포함. completed, 유효 주문일, 기준일 이하. 정제 후 남은 상세 {len(data['completed_order_sales'])}행·금액 있는 주문 {data['completed_order_sales'].order_id.nunique()}건·{total:,}원. 금액은 quantity×unit_price이며 원래 전체 청구금액이나 회계상 순매출이 아니다.",'## 질문과 그래프\n```text\n'+tab(summary)+'\n```','## 범위와 제외 영향\n```text\n'+tab(data['eda_results']['scope'])+'\n```','## 일부 상세가 제외된 주문의 민감도\n```text\n'+tab(data['eda_results']['partial_sensitivity'])+'\n```','## 집계 검증\n```text\n'+tab(data['visualization_validation'])+'\n```','## artist와 원본 집계의 교차 검증\n```text\n'+tab(artist_validation)+'\n```','## 해석 원칙과 한계','카테고리 금액이 크다고 선호도나 이익이 높다고 단정하지 않았다. 월별선은 시간 정렬을 확인하고 누락 월을 임의의 0으로 바꾸지 않았다. 실제 추출 시작·종료일이 없어 경계 월 수집 완전성은 확인할 수 없다. 가격9,999,999원 후보는 전체분포에 보존하고 확대95개와 범위밖1개를 함께 표시했다. 목록 가격은 주문 당시 unit_price와 다르다. 산점도는 인과를, Top10 고객은 충성도를 증명하지 않는다. 상태분포만으로 취소·환불의 원인도 알 수 없다. 그래프별 원본값·관찰·판단·업무의미·한계는 chapter07/chapter07.ipynb에 기록했다.'])+'\n'
