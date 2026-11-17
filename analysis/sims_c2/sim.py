import numpy as np, sys, itertools
from math import comb
from multiprocessing import Pool
P=9  # continuous M0 (0=sr,1=sf, 2..8 rest); + voiced_any binary
def size_d036(N, base):
    L=N//3
    for j in range(7,-1,-1):
        for K in range(j,-1,-1):
            if base+2*j+comb(K,2)<=L: return j,K
def zs(x): s=x.std(0); return (x-x.mean(0))/np.where(s>0,s,1)
def build_Q(M0c,voiced,era,N,variant):
    z=zs(M0c); E=np.column_stack([(era==e).astype(float) for e in (1,2)])
    one=np.ones((N,1))
    if variant=='D036':      # [1, sr, sf, PC1..j, PC^2, products first K PCs] + era + voiced (I2)
        j,K=size_d036(N,6)
        rest=z[:,2:]; U,S,Vt=np.linalg.svd(rest-rest.mean(0),full_matrices=False); pcs=zs(U[:,:j]*S[:j])
        cols=[one,z[:,:2],pcs,pcs**2]+[ (pcs[:,a]*pcs[:,b])[:,None] for a,b in itertools.combinations(range(K),2)]+[E,voiced[:,None]]
    elif variant=='LINFULL': # proposed: full linear M0 always, then sr^2, sf^2, sr*sf, then PC squares in order to budget
        L=N//3; base=[one,z,voiced[:,None],E]; cols=list(base); n=1+P+1+2
        extra=[z[:,0]**2,z[:,1]**2,z[:,0]*z[:,1]]
        rest=z[:,2:]; U,S,Vt=np.linalg.svd(rest-rest.mean(0),full_matrices=False); pcs=zs(U*S)
        extra+= [pcs[:,k]**2 for k in range(7)]
        for e in extra:
            if n+1>L: break
            cols.append(e[:,None]); n+=1
    Q=np.column_stack(cols); return Q
def fitlog(X,y,lam=1.0,it=25):
    X1=np.column_stack([np.ones(len(X)),X]); w=np.zeros(X1.shape[1]); R=lam*np.eye(len(w)); R[0,0]=0
    for _ in range(it):
        p=1/(1+np.exp(-X1@w)); g=X1.T@(p-y)+R@w; H=(X1*(p*(1-p))[:,None]).T@X1+R+1e-9*np.eye(len(w))
        step=np.linalg.solve(H,g); w-=step
        if np.abs(step).max()<1e-8: break
    return w
def auc(s,y):
    r=np.argsort(np.argsort(s))+1.0; n1=y.sum(); n0=len(y)-n1
    return (r[y==1].sum()-n1*(n1+1)/2)/(n1*n0)
def cv_auc(X,y,folds):
    out=[]
    for f in folds:
        s=np.empty(len(y))
        for k in range(5):
            te=f==k; tr=~te; mu=X[tr].mean(0); sd=X[tr].std(0); sd[sd==0]=1
            w=fitlog((X[tr]-mu)/sd,y[tr]); s[te]=np.column_stack([np.ones(te.sum()),(X[te]-mu)/sd])@w
        out.append(auc(s,y))
    return np.mean(out)
def strat_folds(y,rng,rep=2):
    fs=[]
    for _ in range(rep):
        f=np.empty(len(y),int)
        for c in (0,1):
            idx=np.flatnonzero(y==c); rng.shuffle(idx); f[idx]=np.arange(len(idx))%5
        fs.append(f)
    return fs
def one(args):
    N,variant,scen,seed,B=args
    rng=np.random.default_rng(seed)
    Lm=rng.normal(size=(P,P))*0.5+np.eye(P); M0c=rng.normal(size=(N,P))@Lm
    z=zs(M0c); voiced=(z[:,3]>-0.9).astype(float); era=rng.integers(0,3,N)
    nl=np.column_stack([z**2-1]+[ (z[:,a]*z[:,b])[:,None] for a,b in [(0,5),(2,7),(4,8),(1,6)]])
    A=rng.normal(size=(P,7))*0.4; Bm=rng.normal(size=(nl.shape[1],7))*0.25
    M1=z@A+(nl@Bm if scen!='linear' else 0)+rng.normal(size=(N,7))
    if scen=='linear': g=z@rng.normal(size=P)*0.3
    else: g=0.25*(z@rng.normal(size=P))+0.45*(nl@rng.normal(size=nl.shape[1]))/np.sqrt(nl.shape[1])*1.2+0.15*z[:,6]**3
    g=g-np.median(g); y=(rng.uniform(size=N)<1/(1+np.exp(-1.5*g))).astype(float)
    if y.sum()<8 or (1-y).sum()<8: y=(g>np.median(g)).astype(float)
    Q=build_Q(M0c,voiced,era,N,variant)
    Rr=M1-Q@np.linalg.lstsq(Q,M1,rcond=None)[0]
    X0=np.column_stack([z,voiced]); folds=strat_folds(y,rng)
    a0=cv_auc(X0,y,folds); obs=cv_auc(np.column_stack([X0,Rr]),y,folds)-a0
    b=0
    for _ in range(B):
        Rp=Rr.copy()
        for e in range(3):
            idx=np.flatnonzero(era==e); Rp[idx]=Rr[rng.permutation(idx)]
        b+= cv_auc(np.column_stack([X0,Rp]),y,folds)-a0 >= obs
    return (b+1)/(B+1), a0, np.linalg.matrix_rank(Q)
if __name__=='__main__':
    reps=int(sys.argv[1]); B=int(sys.argv[2])
    jobs=[]
    for N in (40,60,80):
        for v in ('D036','LINFULL'):
            for sc in ('nonlinear',):
                jobs+=[(N,v,sc,1000*N+s,B) for s in range(reps)]
    with Pool(4) as pool: res=pool.map(one,jobs,chunksize=4)
    import collections; d=collections.defaultdict(list)
    for j,r in zip(jobs,res): d[j[:3]].append(r)
    for k,v in d.items():
        p=np.array([x[0] for x in v]); print(k,'FPR@.05=%.3f'%(p<=.05).mean(),'(se %.3f)'%np.sqrt(.05*.95/len(p)),'meanAUC0=%.2f'%np.mean([x[1] for x in v]),'rankQ=',v[0][2])
