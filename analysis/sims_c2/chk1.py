import sys; sys.path.insert(0,'/home/user/yct/src')
import numpy as np, pandas as pd
from statsmodels.stats.multitest import multipletests
from yct.interpret import localize as L
from yct.features import m0 as M
from yct.features.networks import spatial_standardize
rng=np.random.default_rng(1)
# BH
for t in range(200):
    m=rng.integers(1,400); p=rng.uniform(size=m)**rng.uniform(0.2,3)
    if t%3==0: p=np.round(p,2)  # ties
    q=L.bh_fdr(p); ref=multipletests(p,method='fdr_bh')[1]
    assert np.allclose(q,ref), t
    o=np.argsort(p); assert np.all(np.diff(q[o])>=-1e-15)
pn=np.array([0.01,np.nan,0.04,0.03]); print('nan BH',L.bh_fdr(pn), multipletests([0.01,0.04,0.03],method='fdr_bh')[1])
print('BH ok vs statsmodels, monotone')
# bootstrap: companies resampled within group
n0,n1=7,9; grp=np.array([0]*n0+[1]*n1); comp=np.array([f'c{i}' for i in range(n0+n1)])
# make maps encode identity
maps=np.zeros((n0+n1,n0+n1)); maps[np.arange(n0+n1),np.arange(n0+n1)]=1.0
# use mean per group: each replicate mean vec; counts*n_g -> integer draws from own group only
for stat in ['diff']:
    for b in L.bootstrap_maps(maps,grp,comp,500,3,stat='diff',groups=(0,1)):
        c1=b[n0:]*n1; c0=-b[:n0]*n0
        assert np.allclose(c1,np.round(c1)) and np.isclose(c1.sum(),n1)
        assert np.allclose(c0,np.round(c0)) and np.isclose(c0.sum(),n0)
print('bootstrap_maps: within-group draws, sizes fixed')
# multi-video companies: cluster resample
comp2=np.array(['a','a','b','c','c','c','d','e','f','g','g','h','i','j','k','l'])
pb=L.company_bootstrap(maps,grp,comp2,n_boot=300,seed=2,stat='diff',groups=(0,1))
B=pb.boots
# videos of same company must have identical weights within replicate
for cname in set(comp2):
    idx=np.flatnonzero(comp2==cname)
    if len(idx)>1: 
        g=grp[idx[0]]; sgn=1 if g==1 else -1
        assert np.allclose(B[:,idx[0]],B[:,idx[1]]), cname
print('company_bootstrap: cluster weights shared; jack rows',pb.jack.shape)
# BCa coverage check, skewed data, mean stat
cov=0; R=300; true=1.0
for r in range(R):
    x=rng.exponential(1,size=(25,1))
    pb=L.company_bootstrap(x,None,np.arange(25),n_boot=2000,seed=r,stat='mean')
    lo,hi=L.bca_interval(pb.estimate,pb.boots,pb.jack,0.95)
    cov+= lo[0]<=true<=hi[0]
print('BCa coverage exp(1) n=25:',cov/R)
cov=0
for r in range(R):
    x=np.r_[rng.exponential(1,size=12),rng.exponential(1,size=30)+0.0][:,None]; g=np.r_[np.zeros(12),np.ones(30)]
    pb=L.company_bootstrap(x,g,np.arange(42),n_boot=2000,seed=r,stat='diff',groups=(0,1))
    lo,hi=L.bca_interval(pb.estimate,pb.boots,pb.jack,0.95); cov+= lo[0]<=0<=hi[0]
print('BCa coverage diff unequal n 12/30:',cov/R)
# rank assert
N=40; m0=pd.DataFrame(rng.normal(size=(N,10)),columns=['rms_db','speech_frac','speech_rate_wps','pitch_mean_hz','luminance_crop','contrast_crop','motion_energy_crop','scene_cuts','face_area_crop_frac','voiced_any'])
m0['voiced_any']=(rng.uniform(size=N)>.2).astype(float)
try:
    M.build_q(m0,['speech_rate_wps','speech_frac','rms_db'],binary=['voiced_any'],forced=['speech_rate_wps','speech_frac'])
except ValueError as e: print('rank assert fires N=40:',e)
print('cols',M.q_column_count(10,1,3,3))
for N in [40,60,69,80]:
    m=pd.DataFrame(rng.normal(size=(N,10)),columns=m0.columns); m['voiced_any']=(rng.uniform(size=N)>.2).astype(float)
    try: r=M.build_q(m,['speech_rate_wps','speech_frac','rms_db'],binary=['voiced_any'],forced=['speech_rate_wps','speech_frac']); print(N,'ok rank',r.rank,r.limit)
    except ValueError as e: print(N,'raise')
# aliased: constant voiced_any
m=pd.DataFrame(rng.normal(size=(90,10)),columns=m0.columns); m['voiced_any']=1.0
r=M.build_q(m,['speech_rate_wps','speech_frac','rms_db'],binary=['voiced_any'],forced=['speech_rate_wps','speech_frac']); print('aliased',r.aliased, r.rank, len(r.columns))
# NaN q
m.iloc[0,0]=np.nan
try: M.build_q(m,['speech_rate_wps','speech_frac','rms_db'],binary=['voiced_any'],forced=['speech_rate_wps','speech_frac'])
except ValueError as e: print('nan:',e)
# near-collinear: numerical rank tolerance
m=pd.DataFrame(rng.normal(size=(90,10)),columns=m0.columns); m['voiced_any']=(rng.uniform(size=90)>.2).astype(float)
m['rms_db']=m['speech_frac']+1e-9*rng.normal(size=90)
r=M.build_q(m,['speech_rate_wps','speech_frac','contrast_crop'],binary=['voiced_any'],forced=['speech_rate_wps','speech_frac']); print('near-collinear rank',r.rank,len(r.columns),r.aliased, 'cond',np.linalg.cond(r.q))
# spatial standardize NaN
mw=np.zeros(100,bool); mw[:5]=True; p=rng.normal(size=(3,100)); p[1,50]=np.nan
try: spatial_standardize(p,mw)
except ValueError as e: print('ss nan:',e)
p[1,50]=0; p[1,2]=np.nan; print('nan on medial wall tolerated:', np.isfinite(spatial_standardize(p,mw)[:,5:]).all())
