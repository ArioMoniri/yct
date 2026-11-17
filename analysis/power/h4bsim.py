import numpy as np
from sklearn.metrics import roc_auc_score
rng=np.random.default_rng(0); N=60; B=199
def run(scale2, shift2, ns=200, rank=False):
    rej=0
    for i in range(ns):
        y=np.r_[np.zeros(30),np.ones(30)]
        s1=0.6*y+rng.standard_normal(N)            # same true AUC
        s2=(0.6*y+rng.standard_normal(N))*scale2+shift2
        if rank: s1=np.argsort(np.argsort(s1)); s2=np.argsort(np.argsort(s2))
        obs=roc_auc_score(y,s1)-roc_auc_score(y,s2)
        nul=[]
        for b in range(B):
            sw=rng.random(N)<.5; a=np.where(sw,s2,s1); c=np.where(sw,s1,s2)
            nul.append(roc_auc_score(y,a)-roc_auc_score(y,c))
        p=(1+np.sum(np.abs(nul)>=abs(obs)))/(B+1); rej+=p<=.05
    return rej/ns
for sc,sh in [(1,2),(3,1)]:
    print("scale",sc,"shift",sh,"raw:",run(sc,sh),"rank:",run(sc,sh,rank=True))
