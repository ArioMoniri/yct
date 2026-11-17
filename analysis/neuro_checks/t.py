import sys,glob,numpy as np
sys.argv=[sys.argv[0],"/dev/null"]
exec(open("/tmp/claude-0/-home-user-yct/796b470d-2b75-56cd-a9e3-264336bb7bb3/scratchpad/neuro_d032/colcheck.py").read().split("cfg = syn")[0])
for f in sorted(glob.glob("/tmp/claude-0/-home-user-yct/796b470d-2b75-56cd-a9e3-264336bb7bb3/scratchpad/neuro_d032/t_*.mp4")):
    p,Y,U,V=decode_raw(f); e=patches(yuv2rgb(Y,U,V,"709","tv"),640,360)-COLS
    print(f.split("/")[-1], "max", np.abs(e).max().round(2), "mean", e.mean().round(2))
