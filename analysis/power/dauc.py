import numpy as np
from scipy.stats import norm
rng=np.random.default_rng(0)
def delong(y,a,b):
    pos,neg=y==1,y==0
    def comps(s):
        X,Y=s[pos],s[neg]
        M=(X[:,None]>Y[None,:])+0.5*(X[:,None]==Y[None,:])
        return M.mean(), M.mean(1), M.mean(0)
    A1,v10a,v01a=comps(a);A2,v10b,v01b=comps(b)
    S10=np.cov(np.vstack([v10a,v10b]));S01=np.cov(np.vstack([v01a,v01b]))
    m,n=pos.sum(),neg.sum()
    var=(S10[0,0]+S10[1,1]-2*S10[0,1])/m+(S01[0,0]+S01[1,1]-2*S01[0,1])/n
    return (A2-A1)/np.sqrt(var)
d0=0.55
for n in (20,30,50):
    for d1 in np.arange(0.3,1.6,0.05):
        hits=0;R=600
        for r in range(R):
            y=np.r_[np.ones(n),np.zeros(n)].astype(int)
            x0=rng.normal(size=2*n)+d0*y; x1=rng.normal(size=2*n)+d1*y
            z=delong(y,x0*d0,x0*d0+x1*d1)
            hits+= z>norm.ppf(.95)  # one-sided (M2>M0)
        if hits/R>=.8:
            dA=norm.cdf(np.hypot(d0,d1)/np.sqrt(2))-norm.cdf(d0/np.sqrt(2))
            print(n,f"oracle: brain-only d1={d1:.2f}, dAUC={dA:.3f} (M0 AUC={norm.cdf(d0/np.sqrt(2)):.3f})");break
