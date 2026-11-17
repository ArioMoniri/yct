import numpy as np, sys, warnings
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import roc_auc_score
from joblib import Parallel, delayed
warnings.filterwarnings("ignore")
N=60; P0=12; K=7; REPS=2; B=99; C=0.3

def oof_auc(X,y,seeds):
    out=[]
    for s in seeds:
        p=np.zeros(len(y))
        for tr,te in StratifiedKFold(5,shuffle=True,random_state=s).split(X,y):
            sc=StandardScaler().fit(X[tr]); m=LogisticRegression(C=C,max_iter=500).fit(sc.transform(X[tr]),y[tr])
            p[te]=m.decision_function(sc.transform(X[te]))
        out.append(roc_auc_score(y,p))
    return np.mean(out)

def resid(Bm,M):
    Z=np.c_[np.ones(len(M)),M]; beta=np.linalg.lstsq(Z,Bm,rcond=None)[0]; return Bm-Z@beta

def gen(rng,scen,eff):
    M=rng.standard_normal((N,P0))
    lin=1.0*M[:,0]+0.6*M[:,1]
    Bm=0.9*M[:,[0]]+0.7*M[:,[2]]+rng.standard_normal((N,K))  # brain correlated with M0
    # sum-to-zero like structure not imposed here
    lp=lin+eff*resid(Bm,M)[:,0]
    if scen=="nonlin": lp=lp+0.8*(M[:,0]**2-1)
    if scen=="nonlin": Bm=Bm+1.0*(M[:,[0]]**2-1)
    y=(rng.random(N)<1/(1+np.exp(-lp))).astype(int)
    # force balanced-ish: ok
    return M,Bm,y

def one(i,scen,eff,obs_kind):
    rng=np.random.default_rng(1000+i)
    M,Bm,y=gen(rng,scen,eff)
    if y.sum()<10 or y.sum()>N-10: return np.nan
    seeds=range(REPS)
    R=resid(Bm,M)
    a0=oof_auc(M,y,seeds)
    Xobs=np.c_[M,Bm] if obs_kind=="raw" else np.c_[M,R]
    obs=oof_auc(Xobs,y,seeds)-a0
    null=[oof_auc(np.c_[M,R[rng.permutation(N)]],y,seeds)-a0 for _ in range(B)]
    return (1+np.sum(np.array(null)>=obs))/(B+1)

if __name__=="__main__":
    scen,eff,obs_kind,ns=sys.argv[1],float(sys.argv[2]),sys.argv[3],int(sys.argv[4])
    ps=np.array(Parallel(n_jobs=4)(delayed(one)(i,scen,eff,obs_kind) for i in range(ns)))
    ps=ps[~np.isnan(ps)]
    print(scen,eff,obs_kind,"n=",len(ps),"rej@.05=",np.mean(ps<=0.05).round(3),"mean p",ps.mean().round(3))
