import json, subprocess, sys
from pathlib import Path
import numpy as np
sys.path[:0] = ["/home/user/yct/src", "/home/user/yct"]
from tests import _synth as syn
from yct.normalize import normalize_video

OUT = Path(sys.argv[1])
K = {"601": (0.299, 0.114), "709": (0.2126, 0.0722)}
COLS = np.array([[200,40,40],[40,180,40],[40,60,200],[210,200,60],[60,190,200],[190,60,190],[128,128,128],[224,172,140]],float)

def rgb2yuv(rgb, m, rng):
    kr, kb = K[m]; x = rgb/255; y = kr*x[...,0]+(1-kr-kb)*x[...,1]+kb*x[...,2]
    cb = (x[...,2]-y)/(2*(1-kb)); cr = (x[...,0]-y)/(2*(1-kr))
    if rng == "tv": return 16+219*y, 128+224*cb, 128+224*cr
    return 255*y, 128+255*cb, 128+255*cr

def yuv2rgb(Y, U, V, m, rng):
    kr, kb = K[m]
    if rng == "tv": y=(Y-16)/219; cb=(U-128)/224; cr=(V-128)/224
    else: y=Y/255; cb=(U-128)/255; cr=(V-128)/255
    r = y+2*(1-kr)*cr; b = y+2*(1-kb)*cb; g = (y-kr*r-kb*b)/(1-kr-kb)
    return np.stack([r,g,b],-1)*255

def make(path, w, h, m, rng, tag):
    pw, ph = w//4, h//2
    rgb = np.zeros((h,w,3))
    for i,c in enumerate(COLS): r_,c_=divmod(i,4); rgb[r_*ph:(r_+1)*ph, c_*pw:(c_+1)*pw]=c
    Y,U,V = rgb2yuv(rgb, m, rng)
    U = U.reshape(h//2,2,w//2,2).mean((1,3)); V = V.reshape(h//2,2,w//2,2).mean((1,3))
    fr = np.concatenate([np.round(a).clip(0,255).astype(np.uint8).ravel() for a in (Y,U,V)]).tobytes()
    raw = path.with_suffix(".yuv"); raw.write_bytes(fr*60)
    extra = []
    if tag:
        pt = "bt709" if tag == "bt709" else "smpte170m"
        extra = ["-colorspace", tag, "-color_primaries", pt, "-color_trc", pt, "-color_range", rng]
    syn.ff("-f","rawvideo","-pix_fmt","yuv420p","-s",f"{w}x{h}","-r","30","-i",str(raw),
           "-f","lavfi","-i","sine=f=330:r=48000:d=2","-shortest","-c:v","libx264","-qp","0","-pix_fmt","yuv420p",
           *extra,"-c:a","aac",str(path))
    raw.unlink()

def decode_raw(path):
    p = json.loads(subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height,color_space,color_range,color_primaries,color_transfer","-of","json",str(path)],capture_output=True,text=True).stdout)["streams"][0]
    w,h = p["width"],p["height"]
    b = subprocess.run(["ffmpeg","-v","error","-i",str(path),"-frames:v","3","-f","rawvideo","-pix_fmt","yuv420p","-"],capture_output=True).stdout
    fs = w*h*3//2; f = np.frombuffer(b[fs:2*fs],np.uint8).astype(float)
    Y = f[:w*h].reshape(h,w); U = f[w*h:w*h+w*h//4].reshape(h//2,w//2); V = f[w*h+w*h//4:].reshape(h//2,w//2)
    return p, Y, U.repeat(2,0).repeat(2,1), V.repeat(2,0).repeat(2,1)

def patches(arr, w, h):
    pw, ph = w//4, h//2; out=[]
    for i in range(8):
        r_,c_=divmod(i,4); out.append(arr[r_*ph+ph//4:r_*ph+3*ph//4, c_*pw+pw//4:c_*pw+3*pw//4].reshape(-1,arr.shape[-1]).mean(0))
    return np.array(out)

cfg = syn.fast_cfg(normalize={"photometric": {"enabled": False}})
cases = [("smpte170m_sd","601","tv","smpte170m",640,360),("bt470bg_sd","601","tv","bt470bg",640,360),
         ("bt709_sd","709","tv","bt709",640,360),("untagged_sd","601","tv",None,640,360),
         ("untagged_hd","709","tv",None,1280,720),("bt709_hd","709","tv","bt709",1280,720),
         ("smpte170m_pc","601","pc","smpte170m",640,360),("untagged_portrait_hd","709","tv",None,720,1280),
         ("untagged_portrait_sd","601","tv",None,480,854)]
for name,m,rng,tag,w,h in cases:
    d = OUT/name; d.mkdir(parents=True, exist_ok=True)
    make(d/"src.mp4", w, h, m, rng, tag)
    rec = normalize_video(d/"src.mp4", d/"out", cfg)
    for key in ("path", "q480_path"):
        p,Y,U,V = decode_raw(rec[key]); ow,oh = p["width"],p["height"]
        e709 = np.abs(patches(yuv2rgb(Y,U,V,"709","tv"),ow,oh)-COLS).max()
        e601 = np.abs(patches(yuv2rgb(Y,U,V,"601","tv"),ow,oh)-COLS).max()
        tags = "/".join(str(p.get(k)) for k in ("color_space","color_primaries","color_transfer","color_range"))
        print(f"{name:22s} {key:9s} rule={rec['color']['rule']:12s} in={rec['color']['in_matrix']}/{rec['color']['in_range']} "
              f"out={ow}x{oh} tags={tags} maxerr709={e709:.2f} (read-as-601 {e601:.2f}) Ymin/max={Y.min():.0f}/{Y.max():.0f} "
              f"untagged_flag={'source_color_untagged' in rec['flags']}", flush=True)
