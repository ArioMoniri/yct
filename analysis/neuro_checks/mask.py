import hashlib, numpy as np, nibabel.freesurfer as fs
A="/root/.cache/yct/atlases/"; N=10242
def rd(p):
    lab,ctab,names=fs.read_annot(p); names=[n.decode() for n in names]; return lab[:N],names
def sha(p): return hashlib.sha256(open(p,"rb").read()).hexdigest()
for f in ["lh.HCPMMP1.annot","rh.HCPMMP1.annot"]: print(f, sha(A+f)[:16])
mw=[];hcp=[];hn={}
for h,dh in (("lh","left"),("rh","right")):
    sl,sn=rd(A+f"{h}.Schaefer2018_400Parcels_7Networks_order.annot")
    hl,hnm=rd(A+f"{h}.HCPMMP1.annot")
    dl,dn=rd(A+f"nilearn/destrieux_surface/{dh}.aparc.a2009s.annot")
    m=(sl<=0)|(np.array(hnm,dtype=object)[np.clip(hl,0,None)]=="???")|(hl<0)|(dl<=0)|np.isin(dl,[i for i,n in enumerate(dn) if n.endswith("Medial_wall")])
    mw.append(m); hcp.append(np.array(hnm,dtype=object)[np.clip(hl,0,None)]); 
mw=np.concatenate(mw); hcp=np.concatenate(hcp); print("union MW", mw.sum())
areas=["OFC","pOFC","11l","13l","TGd","TGv"]
mask=np.isin(hcp,[f"{H}_{a}_ROI" for H in "LR" for a in areas])&~mw
ids=np.flatnonzero(mask).astype("<i4"); print("mask", mask.sum(), "LH", mask[:N].sum(), "RH", mask[N:].sum(), hashlib.sha256(ids.tobytes()).hexdigest())
for a in areas+["TF","TE2a","TE1a","TE2p","PeEc","PreS","EC","PHA1","10pp","a10p","10v","10r","47m","47s","25","s32","PIR","AAIC","TE1m","TE1p","PHT","FFC","STSva","PH"]:
    print(a, [int(((hcp==f"{H}_{a}_ROI")&~mw).sum()) for H in "LR"], "rawMW-lost", [int(((hcp==f"{H}_{a}_ROI")&mw).sum()) for H in "LR"])
np.save("/tmp/claude-0/-home-user-yct/796b470d-2b75-56cd-a9e3-264336bb7bb3/scratchpad/neuro_d032/hcp.npy", hcp); np.save("/tmp/claude-0/-home-user-yct/796b470d-2b75-56cd-a9e3-264336bb7bb3/scratchpad/neuro_d032/mw.npy", mw)
