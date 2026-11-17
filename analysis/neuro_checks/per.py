import sys, numpy as np
sys.argv=[sys.argv[0], "/dev/null"]
exec(open("/tmp/claude-0/-home-user-yct/796b470d-2b75-56cd-a9e3-264336bb7bb3/scratchpad/neuro_d032/colcheck.py").read().split("cfg = syn")[0])
B="/tmp/claude-0/-home-user-yct/796b470d-2b75-56cd-a9e3-264336bb7bb3/scratchpad/neuro_d032/out/"
import glob
for n in ["smpte170m_sd","bt709_sd"]:
    p,Y,U,V=decode_raw(glob.glob(B+n+"/out/*.mp4")[0]); e=patches(yuv2rgb(Y,U,V,"709","tv"),640,360)-COLS
    ps,Ys,Us,Vs=decode_raw(B+n+"/src.mp4"); es=patches(yuv2rgb(Ys,Us,Vs,"601" if "170" in n else "709","tv"),640,360)-COLS
    print(n,"out err\n",np.round(e,1),"\nsrc quant err\n",np.round(es,1))
for n in ["smpte170m_sd"]:
    for f in [glob.glob(B+n+"/out/*.mp4")[0], B+n+"/src.mp4"]:
        p,Y,U,V=decode_raw(f); print(f[-12:], np.round(patches(np.stack([Y,U,V],-1),640,360),2)[[0,6,7]])
# ideal: 601 bytes -> rgb -> 709 bytes (float)
y,u,v=rgb2yuv(COLS,"709","tv"); print("ideal709", np.round(np.stack([y,u,v],-1),2)[[0,6,7]])
