import sys; sys.path.insert(0,'/home/user/yct/src')
import numpy as np
from yct.interpret import localize as L
rng=np.random.default_rng(5); R=400
res={'bca':0,'pct':0,'bca_a_scaled':0}
for r in range(R):
    x0=rng.exponential(1,size=12); x1=rng.exponential(1,size=30); x=np.r_[x0,x1][:,None]; g=np.r_[np.zeros(12),np.ones(30)]
    pb=L.company_bootstrap(x,g,np.arange(42),n_boot=2000,seed=r,stat='diff',groups=(0,1))
    lo,hi=L.bca_interval(pb.estimate,pb.boots,pb.jack,0.95); res['bca']+=lo[0]<=0<=hi[0]
    q=np.quantile(pb.boots[:,0],[.025,.975]); res['pct']+=q[0]<=0<=q[1]
    # influence-scaled acceleration: U = (n_g-1)*(mean_g - jack)
    j=pb.jack[:,0]; j0,j1=j[:12],j[12:]
    U=np.r_[11*(j0.mean()-j0),29*(j1.mean()-j1)]
    jj=np.r_[pb.estimate[0]+U/ (len(U)-1)][:,None]  # pass a jack giving same d-pattern
    # compute a directly
    from statistics import NormalDist; N=NormalDist()
    a=(U**3).sum()/(6*(U**2).sum()**1.5)
    b=pb.boots[:,0]; z0=N.inv_cdf(np.clip((b<pb.estimate[0]).mean(),1e-4,1-1e-4))
    qs=[N.cdf(z0+(z0+za)/(1-a*(z0+za))) for za in (N.inv_cdf(.025),N.inv_cdf(.975))]
    lo2,hi2=np.quantile(b,qs); res['bca_a_scaled']+=lo2<=0<=hi2
print({k:v/R for k,v in res.items()})
