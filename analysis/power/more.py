import numpy as np
from scipy.stats import norm, t, nct
za,zb=norm.ppf(.975),norm.ppf(.8)
def se(A,n1,n2):
    q1=A/(2-A);q2=2*A*A/(1+A)
    return np.sqrt((A*(1-A)+(n1-1)*(q1-A*A)+(n2-1)*(q2-A*A))/(n1*n2))
def aucmde(n1,n2):
    for A in np.arange(.5,.99,.0005):
        if (A-.5)>=za*se(.5,n1,n2)+zb*se(A,n1,n2): return A
for Ntot in (60,80,100,150,200):
    h=int(round(Ntot*.2/2))
    print("Ntot",Ntot,"holdout per class",h,"holdout AUC MDE",round(aucmde(h,h),3),"SE@.70",round(se(.7,h,h),3),
          "| full-N AUC MDE",round(aucmde(Ntot//2,Ntot//2),3))
# TOST power, true d=0, bounds +-delta, alpha .05
def tost_power(n,delta,alpha=.05,R=20000,rng=np.random.default_rng(1)):
    df=2*n-2; tc=t.ppf(1-alpha,df); hit=0
    x=rng.normal(size=(R,n));y=rng.normal(size=(R,n))
    m=x.mean(1)-y.mean(1); sp=np.sqrt((x.var(1,ddof=1)+y.var(1,ddof=1))/2); s=sp*np.sqrt(2/n)
    return np.mean(((m+delta*sp)/s>tc)&((m-delta*sp)/s<-tc))  # standardized bounds approx
for n in (20,30,50):
    print("TOST n/group",n,{d:round(tost_power(n,d),2) for d in (0.5,0.6,0.8)})
