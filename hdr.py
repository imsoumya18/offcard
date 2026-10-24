#!/usr/bin/env python3
"""ShotLoft HDR: merge a set of exposure-bracketed Sony RAW photos into one natural-looking photo.

Needs NumPy, rawpy (LibRaw) and Pillow; the ShotLoft app bundles them. The engine (engine.py) finds
the bracket sets; this module merges one set. How it works, in short (DEVELOPMENT.md has the why):

  1. Decode   each RAW to linear camera RGB. A pixel's colour counts as clipped if its RAW value is
              within 2.5% of white (Sony's lossy RAW smears the clip level by about +-100).
  2. Noise    measure each frame's sensor noise (variance = a*signal + b) from its two green pixels
              in every 2x2 Bayer block, which see the same light.
  3. Align    handheld frames to the middle exposure: phase correlation of 256 px tiles on
              exposure-equalised luminance, then a robust affine fit (shift, rotation, scale).
  4. Ratios   measure the real exposure ratios from the pixels (EXIF shutter speeds are nominal and
              can be ~5% off).
  5. Merge    with weights 1/variance (statistically the best estimate), per pixel, fading out
              near a frame's clipped areas. Where a frame disagrees with the reference by more than
              its noise (and, at edges, a little misalignment) can explain, something moved: that
              frame is left out there (no ghosts). The reference is the middle exposure, or the next
              darker frame where the middle one is clipped.
  6. Rebuild  colours clipped in every frame toward white, never magenta.
  7. Tone     fuse virtual exposures of the merged image (Mertens exposure fusion), so the result
              looks natural with no halos, and apply that as a smooth gain to the full-size image,
              with less saturation where pixels are lifted most.
  8. Finish   defringe violet edges next to very bright areas, and smooth colour noise.

The analysis (steps 2-5) runs on half-size images; the merge itself runs at full size, in strips.

  python3 hdr.py merge OUT_DIR FILE.ARW...  [--tiff]   merge one set
  python3 hdr.py selftest                               run the built-in test on synthetic frames
"""
import os
import sys
import time

import numpy as np

f32 = np.float32
SRGB2XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                     [0.2126729, 0.7151522, 0.0721750],
                     [0.0193339, 0.1191920, 0.9503041]])
LUMA = np.array([0.2126, 0.7152, 0.0722], f32)
CLIP_MARGIN = 0.025   # of the white level
ALIGN_SIGMA = 1.5    # half-size pixels of alignment error (or motion blur) the ghost test allows for at edges
GHOST_T = 3.0         # mean squared difference, in units of the expected noise, where a frame is fully rejected
STRIP = 256           # rows per strip in the full-size merge


# ---------------------------------------------------------------- small image tools (NumPy only)

def box(x, r):
    """Mean over a (2r+1) x (2r+1) window, edges repeated."""
    pad = [(r + 1, r)] * 2 + [(0, 0)] * (x.ndim - 2)
    c = np.pad(x.astype(np.float64), pad, mode="edge").cumsum(0).cumsum(1)
    n = 2 * r + 1
    return ((c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]) / (n * n)).astype(f32)


def blur5(x):
    """Separable [1 4 6 4 1]/16 blur, edges mirrored."""
    k = (1 / 16, 4 / 16, 6 / 16, 4 / 16, 1 / 16)
    for ax in (0, 1):
        p = np.pad(x, [(2, 2) if a == ax else (0, 0) for a in range(x.ndim)], mode="reflect")
        n = x.shape[ax]
        x = sum(w * np.take(p, range(i, i + n), axis=ax) for i, w in enumerate(k))
    return x.astype(f32)


def down(x):
    return blur5(x)[::2, ::2]


def up(x, shape):
    """Burt-Adelson expand to shape (about twice the size)."""
    out = np.zeros(shape[:2] + x.shape[2:], f32)
    out[::2, ::2] = x[: (shape[0] + 1) // 2, : (shape[1] + 1) // 2]
    return blur5(out) * 4


def sample(img, qy, qx):
    """Bilinear sample of img (H, W[, C]) at float coordinates, edges repeated."""
    H, W = img.shape[:2]
    qy = np.clip(qy, 0, H - 1.001)
    qx = np.clip(qx, 0, W - 1.001)
    y0, x0 = qy.astype(np.int32), qx.astype(np.int32)
    fy, fx = qy - y0, qx - x0
    if img.ndim == 3:
        fy, fx = fy[..., None], fx[..., None]
    a, b = img[y0, x0], img[y0, x0 + 1]
    c, d = img[y0 + 1, x0], img[y0 + 1, x0 + 1]
    return ((a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy).astype(f32)


def mapping(M, t):
    """Where a reference pixel (y, x) is in a frame: the affine M p + t."""
    def q(yy, xx):
        return M[0, 0] * yy + M[0, 1] * xx + t[0] + 0 * xx, M[1, 0] * yy + M[1, 1] * xx + t[1] + 0 * yy
    return q


def warp(img, q):
    """img resampled so that output pixel p shows input point q(p) (in strips, to save memory)."""
    H, W = img.shape[:2]
    out = np.empty(img.shape, f32)
    xx = np.arange(W, dtype=f32)[None, :]
    for y0 in range(0, H, STRIP):
        yy = np.arange(y0, min(H, y0 + STRIP), dtype=f32)[:, None]
        out[y0:y0 + STRIP] = sample(img, *q(yy, xx))
    return out


def dilate(m):
    p = np.pad(m, 1, mode="edge")
    out = m.copy()
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            out |= p[dy:dy + m.shape[0], dx:dx + m.shape[1]]
    return out


def gamma(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055).astype(f32)


def ungamma(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4)).astype(f32)


# ---------------------------------------------------------------- frames

class Frame:
    """One photo of the set: half-size analysis data, plus the full-size linear image."""

    def __init__(self, name, half, satc, g1, g2, full, full_scale, t, bias, wb, cam_to_srgb, flip=0, meta=None):
        self.name, self.half, self.satc, self.g1, self.g2 = name, half, satc, g1, g2
        self.full, self.full_scale = full, full_scale   # uint16 (H, W, 3); value * full_scale = linear 0..1
        self.t, self.bias, self.wb, self.cam_to_srgb = t, bias, wb, cam_to_srgb
        self.flip, self.meta = flip, meta or {}
        self.sat = satc.any(-1)
        self.q, self.k = mapping(np.eye(2), np.zeros(2)), 1.0


def half_from_bayer(raw, pattern, desc, black, white):
    """2x2-binned linear camera RGB in 0..1, clipped-colour masks, and the two greens."""
    H, W = raw.shape[0] // 2 * 2, raw.shape[1] // 2 * 2
    raw = raw[:H, :W]
    ch, sat = {}, {}
    for i in (0, 1):
        for j in (0, 1):
            c = pattern[i][j]
            p = raw[i::2, j::2].astype(f32)
            name = desc[c]
            sat[name] = sat.get(name, False) | (p >= white - CLIP_MARGIN * (white - black[c]))
            ch.setdefault(name, []).append((p - black[c]) / (white - black[c]))
    g1, g2 = ch["G"]
    half = np.stack([ch["R"][0], (g1 + g2) / 2, ch["B"][0]], -1)
    satc = np.stack([dilate(sat[k]) for k in "RGB"], -1)
    return half, satc, g1, g2


def cam_to_srgb_matrix(xyz2cam):
    cam_rgb = np.asarray(xyz2cam, np.float64)[:3] @ SRGB2XYZ
    cam_rgb /= cam_rgb.sum(1, keepdims=True)
    return np.linalg.inv(cam_rgb).astype(f32)


def load_raw(path):
    """Decode a RAW file into a Frame."""
    import rawpy
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    with open(path, "rb") as f:
        exif = _engine()._tiff_fields(f, 0)
    with rawpy.imread(path) as r:
        raw = r.raw_image_visible
        desc = r.color_desc.decode()
        black = [float(b) for b in r.black_level_per_channel]
        white = float(r.white_level)
        pattern = r.raw_pattern.tolist()
        half, satc, g1, g2 = half_from_bayer(raw, pattern, desc, black, white)
        wb = np.array(r.camera_whitebalance[:3], f32)
        full = r.postprocess(demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD, use_camera_wb=False,
                             user_wb=[1, 1, 1, 1], output_color=rawpy.ColorSpace.raw, gamma=(1, 1),
                             no_auto_bright=True, output_bps=16, highlight_mode=rawpy.HighlightMode.Clip,
                             user_flip=0)
        # LibRaw scales the RAW values by its own factor: measure it at green photosites.
        gi, gj = [(i, j) for i in (0, 1) for j in (0, 1) if desc[pattern[i][j]] == "G"][0]
        rv = raw[gi::2, gj::2][::4, ::4].astype(f32) - black[pattern[gi][gj]]
        fv = full[gi::2, gj::2, 1][::4, ::4].astype(f32)
        ok = (rv > 0.02 * white) & (rv < 0.8 * white)
        scale = float(np.median(fv[ok] / rv[ok])) if ok.sum() > 100 else 65535 / (white - black[1])
        full_scale = 1.0 / (scale * (white - black[1]))
        flip = r.sizes.flip
        xyz2cam = r.rgb_xyz_matrix
    return Frame(os.path.basename(path), half, satc, g1, g2, full, full_scale,
                 float(exif.get("exposure_time", 1.0)), float(exif.get("bias", 0.0)),
                 wb / wb[1], cam_to_srgb_matrix(xyz2cam), flip, exif)


_ENGINE = None


def _engine():
    global _ENGINE
    if _ENGINE is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "shotloft_engine_hdr", os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine.py"))
        _ENGINE = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_ENGINE)
    return _ENGINE


# ---------------------------------------------------------------- noise, alignment

def noise_model(fr):
    """variance = a*signal + b, from the difference of the two greens of each Bayer block."""
    s = ((fr.g1 + fr.g2) / 2)[~fr.sat][::7]
    d = (fr.g1 - fr.g2)[~fr.sat][::7]
    xs, vs = [], []
    edges = np.geomspace(2e-4, 0.8, 30)
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (s >= lo) & (s < hi)
        if m.sum() > 500:
            xs.append(s[m].mean())
            vs.append(np.median(d[m] ** 2) / 0.455 / 2)  # median of a squared normal is 0.455 sigma^2
    if len(xs) < 3:
        return 1e-4, 1e-7
    xs, vs = np.array(xs), np.array(vs)
    A = np.stack([xs, np.ones_like(xs)], 1)
    a, b = np.linalg.lstsq(A / vs[:, None], np.ones_like(vs), rcond=None)[0]  # relative-error fit
    return max(float(a), 1e-7), max(float(b), 1e-10)


def phasecorr(a, b):
    """Shift d with a(x) ~= b(x - d), sub-pixel, and the peak strength."""
    win = np.outer(np.hanning(a.shape[0]), np.hanning(a.shape[1])).astype(f32)
    A = np.fft.rfft2((a - a.mean()) * win)
    B = np.fft.rfft2((b - b.mean()) * win)
    R = A * np.conj(B)
    R /= np.abs(R) + 1e-12
    r = np.fft.irfft2(R, s=a.shape)
    iy, ix = np.unravel_index(np.argmax(r), r.shape)

    def sub(m, c, p):
        den = m - 2 * c + p
        return 0.5 * (m - p) / den if den else 0.0
    dy = iy + sub(r[(iy - 1) % r.shape[0], ix], r[iy, ix], r[(iy + 1) % r.shape[0], ix])
    dx = ix + sub(r[iy, (ix - 1) % r.shape[1]], r[iy, ix], r[iy, (ix + 1) % r.shape[1]])
    if dy > a.shape[0] / 2:
        dy -= a.shape[0]
    if dx > a.shape[1] / 2:
        dx -= a.shape[1]
    return dy, dx, float(r[iy, ix])


def align(ref_L, L, k, lo, hi, tile=256):
    """Affine (M, t) so that ref pixel p shows frame point M p + t. Both are half-size luminance;
    the frame is k times brighter. Compared in log luminance, clamped to [lo, hi] where both see it."""
    a = np.log(np.clip(ref_L, lo, hi))
    b = np.log(np.clip(L / k, lo, hi))
    s = 4
    h4, w4 = a.shape[0] // s * s, a.shape[1] // s * s
    a4 = a[:h4, :w4].reshape(h4 // s, s, -1, s).mean((1, 3))
    b4 = b[:h4, :w4].reshape(h4 // s, s, -1, s).mean((1, 3))
    gy, gx, _ = phasecorr(a4, b4)
    d0 = np.array([gy * s, gx * s])
    P, Q, Wt = [], [], []
    H, W = a.shape
    for y in range(tile // 2, H - tile, tile // 2):
        for x in range(tile // 2, W - tile, tile // 2):
            oy, ox = int(round(y - d0[0])), int(round(x - d0[1]))
            if oy < 0 or ox < 0 or oy + tile > H or ox + tile > W:
                continue
            ta, tb = a[y:y + tile, x:x + tile], b[oy:oy + tile, ox:ox + tile]
            if ta.std() < 0.05:
                continue  # flat, or all outside the shared range
            dy, dx, pk = phasecorr(ta, tb)
            P.append((y + tile / 2, x + tile / 2))
            Q.append((oy + tile / 2 - dy, ox + tile / 2 - dx))
            Wt.append(pk)
    P, Q, Wt = np.array(P).reshape(-1, 2), np.array(Q).reshape(-1, 2), np.array(Wt)
    keep = Wt > 0.05
    if keep.sum() < 6:  # too dark or too flat for a model: whole-frame shift only
        M, t, stats = np.eye(2), -d0, {"rotation_deg": 0.0, "tiles": int(keep.sum())}
    else:
        X = np.hstack([P, np.ones((len(P), 1))])
        for _ in range(4):  # least squares, dropping tiles that disagree (moving things, repeats)
            sol = np.linalg.lstsq(X[keep] * Wt[keep, None], Q[keep] * Wt[keep, None], rcond=None)[0]
            res = np.linalg.norm(X @ sol - Q, axis=1)
            keep = (res < max(1.0, 3 * np.median(res[keep]))) & (Wt > 0.05)
        M, t = sol[:2].T, sol[2]
        rot = np.degrees(np.arctan2(M[1, 0] - M[0, 1], M[0, 0] + M[1, 1]))
        stats = {"rotation_deg": round(float(rot), 3), "tiles": int(keep.sum())}
    c = np.array([H / 2, W / 2])
    stats["shift_px"] = (2 * (M @ c + t - c)).round(1).tolist()
    return mapping(M, t), stats


# ---------------------------------------------------------------- merge

def lum(x):
    return x.mean(-1)


def analyse(frames, progress=lambda f, s: None):
    """Align, measure exposure ratios and noise, and build each frame's per-colour weights (half size).
    Returns (ref index, darkest-first order, weights, info)."""
    n = len(frames)
    ref = int(np.argmin([abs(f.bias) for f in frames]))
    order = list(np.argsort([f.t for f in frames]))
    R = frames[ref]
    RL = lum(R.half)
    info = {"reference": R.name, "frames": []}
    for i, f in enumerate(frames):
        f.noise = noise_model(f)
        f.g1 = f.g2 = None
        if i != ref:
            k0 = f.t / R.t
            hi = min(0.9, 0.9 / k0)
            lo = max(0.004, 0.008 / k0)
            f.q, st = align(RL, lum(f.half), k0, lo, hi)
            f.halfw = warp(f.half, f.q)
            f.satw = warp(f.satc.astype(f32), f.q) > 0.01
            # Pixels chosen by the reference alone (choosing by the noisy frame biases the ratio),
            # where both frames are well exposed and unclipped; smoothed to beat down noise.
            Lw, Rb = box(lum(f.halfw), 2), box(RL, 2)
            ok = ((Rb > 0.03) & (Rb < 0.7) & (Rb * k0 > 0.03) & (Rb * k0 < 0.7)
                  & ~dilate(f.satw.any(-1) | R.satc.any(-1)))
            f.k = float(np.median(Lw[ok] / Rb[ok])) if ok.sum() > 1000 else k0
            f.halfw /= f.k  # from here on, every frame is in the reference's brightness units
            f.half = f.satc = None
            info["frames"].append({"name": f.name, "bias": f.bias, "ratio_exif": round(k0, 4),
                                   "ratio_measured": round(f.k, 4), **st})
        else:
            f.halfw, f.satw = f.half, f.satc
            info["frames"].append({"name": f.name, "bias": f.bias, "reference": True})
        progress((i + 1) / n * 0.5, "Aligning")

    E = [f.halfw for f in frames]
    Rs = box(lum(E[ref]), 2)
    var = []
    for f in frames:
        a, b = f.noise
        x = np.clip(Rs * f.k, 0, 1)  # noise-free estimate of this frame's signal
        var.append(((a * x + b) / f.k ** 2).astype(f32))

    # The reference: the middle exposure; where it's clipped, the next darker frame, and so on.
    sat_any = [f.satw.any(-1) for f in frames]
    refE, refV = E[ref].copy(), var[ref].copy()
    refidx = np.full(RL.shape, ref, np.int8)
    clipped = sat_any[ref].copy()
    for i in [j for j in order[::-1] if frames[j].t < R.t]:
        m = clipped & ~sat_any[i]
        refE[m], refV[m], refidx[m] = E[i][m], var[i][m], i
        clipped &= sat_any[i]

    # Weights are per pixel, so a pixel's three colours always come from the same frames (mixing
    # sources per colour turns small mismatches into colour speckle), and they fade out over a few
    # pixels next to a frame's clipped areas instead of switching hard. Only where every frame is
    # clipped somewhere (a window, a lamp) do colours merge separately, keeping what isn't clipped.
    gw, pix, ghosts = [], [], {}
    refL = lum(refE)
    # At edges, a residual misalignment of ~half a pixel (or a little motion blur in a long exposure)
    # makes frames differ by far more than noise. Expect that too, so edges aren't taken for movement.
    p = np.pad(refL, 1, mode="edge")
    grad2 = ((p[2:, 1:-1] - p[:-2, 1:-1]) ** 2 + (p[1:-1, 2:] - p[1:-1, :-2]) ** 2) / 4
    align_var = box(grad2, 1) * ALIGN_SIGMA ** 2
    for i, f in enumerate(frames):
        z = box((lum(E[i]) - refL) ** 2 / (var[i] + refV + align_var), 4)
        g = np.clip((GHOST_T - z) / (GHOST_T - 1), 0, 1)
        g[refidx == i] = 1.0
        ghosts[f.name] = round(float(((g < 0.5) & ~sat_any[i]).mean() * 100), 2)
        gw.append((g / var[i]).astype(f32))
        pix.append(gw[-1] * np.clip(1 - 2 * box(sat_any[i].astype(f32), 2), 0, 1))
        progress(0.5 + (i + 1) / n * 0.5, "Aligning")
    per_colour = (sum(pix) <= 0)[..., None]
    weights = [np.where(per_colour, np.where(f.satw, 0, g[..., None]), w[..., None]).astype(f32)
               for f, g, w in zip(frames, gw, pix)]
    info["moved_pct"] = ghosts
    return ref, order, weights, info


def combine(stacks, weights, frames, ref, order):
    """Weighted mean of aligned frames (same shapes); colours clipped everywhere rebuilt toward white."""
    num = sum(s * w for s, w in zip(stacks, weights))
    den = sum(weights)
    zero = den <= 0
    dk = order[0]
    num = np.where(zero, stacks[dk], num)
    out = num / np.where(zero, 1, den)
    if zero.any():
        wb = frames[ref].wb
        v = out * wb
        unc = np.where(zero, -np.inf, v).max(-1, keepdims=True)
        v = np.where(zero, np.maximum(v, np.where(np.isfinite(unc), unc, v)), v)
        out = v / wb
    return out.astype(f32), zero


def merge_full(frames, ref, order, weights, progress=lambda f, s: None):
    """The merge at full size, strip by strip. Weights come from the half-size analysis."""
    H, W = frames[ref].full.shape[:2]
    hh, hw = weights[0].shape[:2]
    out = np.empty((H, W, 3), f32)
    xs = np.arange(W, dtype=f32)
    for y0 in range(0, H, STRIP):
        y1 = min(H, y0 + STRIP)
        yy, xx = np.meshgrid(np.arange(y0, y1, dtype=f32), xs, indexing="ij")
        hy, hx = (yy + 0.5) / 2 - 0.5, (xx + 0.5) / 2 - 0.5   # full -> half pixel centres
        stacks, ws = [], []
        for f, w in zip(frames, weights):
            ws.append(sample(w, hy, hx))
            if f is frames[ref]:
                stacks.append(f.full[y0:y1].astype(f32) * f.full_scale)
                continue
            # half-size mapping -> full size: q_full = 2 q(p_half) + 0.5 with p_half = (p_full - 0.5) / 2
            qy_h, qx_h = f.q(hy, hx)
            qy, qx = 2 * qy_h + 0.5, 2 * qx_h + 0.5
            r0 = int(max(0, np.floor(qy.min()) - 1))
            r1 = int(min(H, np.ceil(qy.max()) + 2))
            src = f.full[r0:r1].astype(f32) * f.full_scale
            stacks.append(sample(src, qy - r0, qx) / f.k)
        out[y0:y1], _ = combine(stacks, ws, frames, ref, order)
        progress(y1 / H, "Merging")
    return out


# ---------------------------------------------------------------- tone mapping

def mertens(imgs, sigma=0.2):
    """Exposure fusion (Mertens, Kautz & Van Reeth 2007) of gamma-encoded images in 0..1."""
    Ws = []
    for I in imgs:
        g = I.mean(-1)
        p = np.pad(g, 1, mode="edge")
        C = np.abs(p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:] - 4 * g)
        S = I.std(-1)
        Ex = np.exp(-((I - 0.5) ** 2) / (2 * sigma ** 2)).prod(-1)
        Ws.append(C * S * Ex + 1e-12)
    Ws = np.array(Ws)
    Ws /= Ws.sum(0)
    levels = max(1, int(np.log2(min(imgs[0].shape[:2]))) - 3)
    out = None
    for I, Wt in zip(imgs, Ws):
        cur, w, lp, gp = I, Wt.astype(f32), [], []
        for _ in range(levels):
            nxt = down(cur)
            lp.append(cur - up(nxt, cur.shape))
            gp.append(w)
            cur, w = nxt, down(w)
        lp.append(cur)
        gp.append(w)
        blended = [l * g[..., None] for l, g in zip(lp, gp)]
        out = blended if out is None else [o + b for o, b in zip(out, blended)]
    img = out[-1]
    for l in reversed(out[:-1]):
        img = up(img, l.shape) + l
    return np.clip(img, 0, 1)


def exposure_plan(Y):
    """Base gain and the virtual exposures (EV) that span the scene, from linear luminance."""
    small = Y[::4, ::4]
    base = 0.18 / float(np.exp(np.mean(np.log(small + 1e-6))))
    Ys = box(Y[::2, ::2], 2)  # ignore lone hot pixels, keep small bright areas like a window
    p_hi = float(np.percentile(Ys, 99.95)) * base
    p_lo = float(np.percentile(small, 3)) * base
    e_lo = min(0.0, np.log2(0.95 / max(p_hi, 1e-6)))
    e_hi = max(0.0, min(3.0, np.log2(0.10 / max(p_lo, 1e-6))))
    n = int(np.ceil((e_hi - e_lo) / 1.5)) + 1
    return base, np.linspace(e_lo, e_hi, max(n, 2))


def tone_gain(lin_half):
    """Per-pixel gain (half size) that turns base-exposed linear sRGB into the fused look."""
    Y = lin_half @ LUMA
    base, evs = exposure_plan(Y)
    fused = mertens([gamma(lin_half * base * 2 ** e) for e in evs])
    Yf = ungamma(fused) @ LUMA
    gain = (Yf + 1e-5) / (Y * base + 1e-5)
    return blur5(gain.astype(f32)), base, evs


def tone_apply(lin, g):
    """Linear sRGB (at base exposure) times the tone gain, then gamma. Colour is corrected the way
    Mantiuk et al. (2009) suggest: the more a pixel is brightened, the less its saturation grows,
    so lifted shadows don't turn garish or show their colour noise."""
    Y = lin @ LUMA
    s = np.clip(1 - 0.12 * np.log2(np.maximum(g, 1)), 0.6, 1)[..., None]
    ratio = (lin + 1e-3) / (Y[..., None] + 1e-3)
    return gamma(ratio ** s * (Y * g)[..., None])


def to_srgb_linear(cam, fr):
    return np.maximum((cam * fr.wb) @ fr.cam_to_srgb.T, 0).astype(f32)


def bin2(x):
    h, w = x.shape[0] // 2 * 2, x.shape[1] // 2 * 2
    return x[:h, :w].reshape(h // 2, 2, w // 2, 2, *x.shape[2:]).mean((1, 3))


# ---------------------------------------------------------------- output

def orient(img, flip):
    """Rotate pixels upright from LibRaw's flip code (0 none, 3 = 180, 5 = 90 left, 6 = 90 right)."""
    return {3: np.rot90(img, 2), 5: np.rot90(img, 1), 6: np.rot90(img, -1)}.get(flip, img)


def save_jpeg(rgb8, path, fr, quality=95):
    from PIL import Image
    from PIL.TiffImagePlugin import IFDRational
    im = Image.fromarray(rgb8)
    ex = im.getexif()
    m = fr.meta
    ex[0x010F] = "SONY"
    if m.get("model"):
        ex[0x0110] = m["model"]
    ex[0x0131] = f"ShotLoft {_engine().__version__} HDR"
    ex[0x0112] = 1
    if m.get("taken"):
        ex[0x0132] = m["taken"]
    sub = ex.get_ifd(0x8769)
    if m.get("taken"):
        sub[0x9003] = m["taken"]
        sub[0x9004] = m["taken"]
    if m.get("fnumber"):
        sub[0x829D] = IFDRational(round(m["fnumber"] * 10), 10)
    if m.get("focal_length"):
        sub[0x920A] = IFDRational(round(m["focal_length"] * 10), 10)
    if m.get("iso"):
        sub[0x8827] = int(m["iso"])
    tmp = path + ".partial"
    im.save(tmp, "JPEG", quality=quality, exif=ex.tobytes())
    os.replace(tmp, path)


def save_tiff16(rgb16, path):
    """16-bit RGB TIFF, deflate-compressed with a horizontal predictor (Lightroom, Photoshop, etc.)."""
    import struct
    import zlib
    H, W, _ = rgb16.shape
    rows = 16
    strips = []
    for y in range(0, H, rows):
        s = rgb16[y:y + rows].astype(np.int32)
        d = s.copy()
        d[:, 1:] -= s[:, :-1]                       # predictor 2: each sample minus its left neighbour
        strips.append(zlib.compress(d.astype("<u2").tobytes(), 6))
    offsets, o = [], 8
    for s in strips:
        offsets.append(o)
        o += len(s)
    n = len(strips)
    bps_off = o                                     # after the image data: bits/sample, offsets, counts, IFD
    so_off = bps_off + 6
    sc_off = so_off + 4 * n
    ifd_off = sc_off + 4 * n
    tags = [(256, 4, 1, W), (257, 4, 1, H), (258, 3, 3, bps_off), (259, 3, 1, 8), (262, 3, 1, 2),
            (273, 4, n, so_off), (277, 3, 1, 3), (278, 4, 1, rows), (279, 4, n, sc_off),
            (284, 3, 1, 1), (317, 3, 1, 2)]
    ifd = struct.pack("<H", len(tags))
    for tag, typ, cnt, val in tags:
        ifd += struct.pack("<HHIHH", tag, typ, cnt, val, 0) if typ == 3 and cnt == 1 else \
            struct.pack("<HHII", tag, typ, cnt, val)
    ifd += struct.pack("<I", 0)
    tmp = path + ".partial"
    with open(tmp, "wb") as f:
        f.write(b"II*\0" + struct.pack("<I", ifd_off))
        for s in strips:
            f.write(s)
        f.write(struct.pack("<3H", 16, 16, 16) + struct.pack(f"<{n}I", *offsets)
                + struct.pack(f"<{n}I", *[len(s) for s in strips]) + ifd)
    os.replace(tmp, path)


# ---------------------------------------------------------------- the whole set

TONE_SCALE = 4  # tone mapping is worked out at 1/4 size: its gain is smooth, and full-size detail passes through


def merge_frames(frames, progress=lambda f, s: None, tone_scale=TONE_SCALE):
    """Merge decoded frames. Returns (8-bit sRGB image, merged full-size camera RGB, base gain, ref, info).
    Frees each frame's full-size image once it's merged."""
    t0 = time.time()
    ref, order, weights, info = analyse(frames, lambda f, s: progress(0.05 + 0.25 * f, s))
    R = frames[ref]

    # Tone mapping is decided on a small merge, then applied to the full-size one as a smooth gain.
    merged_half, _ = combine([f.halfw for f in frames], weights, frames, ref, order)
    small = merged_half if tone_scale == 2 else bin2(merged_half)
    gain, base, evs = tone_gain(to_srgb_linear(small, R))
    fringe_zone, clean = fringe_maps(merged_half, R, gain, base, tone_scale)
    del merged_half, small
    progress(0.4, "Tone mapping")

    full = merge_full(frames, ref, order, weights, lambda f, s: progress(0.4 + 0.45 * f, s))
    for f in frames:
        f.full = None
    H, W = full.shape[:2]
    out8 = np.empty((H, W, 3), np.uint8)
    xs = np.arange(W, dtype=f32)
    for y0 in range(0, H, STRIP):
        y1 = min(H, y0 + STRIP)
        yy, xx = np.meshgrid(np.arange(y0, y1, dtype=f32), xs, indexing="ij")
        g = sample(gain, (yy + 0.5) / tone_scale - 0.5, (xx + 0.5) / tone_scale - 0.5)
        o = tone_apply(to_srgb_linear(full[y0:y1], R) * base, g)
        # Defringe: violet edges next to very bright areas take the colour of their surroundings.
        hy, hx = (yy + 0.5) / 2 - 0.5, (xx + 0.5) / 2 - 0.5
        v = (violet(o) * sample(fringe_zone, hy, hx))[..., None]
        c = sample(clean, hy, hx)
        level = (o[..., :1] + o[..., 1:2]) / (c[..., :1] + c[..., 1:2] + 1e-3)  # from red + green: blue is the fringe
        o = o * (1 - v) + c * level * v
        out8[y0:y1] = (np.clip(o, 0, 1) * 255 + 0.5).astype(np.uint8)
    out8 = chroma_denoise(out8)
    progress(0.9, "Saving")
    info.update(virtual_evs=[round(float(e), 2) for e in evs], base=base, seconds=round(time.time() - t0, 1))
    return orient(out8, R.flip), full, base, ref, info


def violet(o):
    """How violet/blue-fringe-like each pixel of a gamma-encoded image is, 0..1."""
    r, g, b = o[..., 0], o[..., 1], o[..., 2]
    return np.clip((b - g - 0.06) / 0.15, 0, 1) * np.clip((b - r + 0.15) / 0.15, 0, 1)


def fringe_maps(merged_half, R, gain, base, tone_scale):
    """Half-size maps for defringing: where fringes can be (next to areas brighter than the middle
    exposure could hold), and the colour (rgb / luma) of the surroundings, ignoring violet pixels."""
    zone = np.clip(box((lum(merged_half) > 0.95).astype(f32), 12) * 4, 0, 1)
    H, W = zone.shape
    o = np.empty(merged_half.shape, f32)
    xs = np.arange(W, dtype=f32)
    for y0 in range(0, H, STRIP):
        yy, xx = np.meshgrid(np.arange(y0, min(H, y0 + STRIP), dtype=f32), xs, indexing="ij")
        g = sample(gain, (yy + 0.5) * 2 / tone_scale - 0.5, (xx + 0.5) * 2 / tone_scale - 0.5)
        o[y0:y0 + STRIP] = tone_apply(to_srgb_linear(merged_half[y0:y0 + STRIP], R) * base, g)
    keep = 1 - violet(o)
    chroma = o / (o @ LUMA + 1e-3)[..., None]
    clean = box(chroma * keep[..., None], 8) / (box(keep, 8) + 1e-6)[..., None]
    return zone, clean.astype(f32)


def chroma_denoise(rgb8, radius=1.5):
    """Smooth colour, not brightness: removes colour grain in lifted shadows, keeps detail."""
    from PIL import Image, ImageFilter
    y, cb, cr = Image.fromarray(rgb8).convert("YCbCr").split()
    blur = ImageFilter.GaussianBlur(radius)
    return np.asarray(Image.merge("YCbCr", (y, cb.filter(blur), cr.filter(blur))).convert("RGB"))


def tiff_image(full, base, fr):
    """16-bit sRGB for editing: the merge with only a gentle global highlight roll-off (Reinhard)."""
    Y = to_srgb_linear(full[::4, ::4], fr) @ LUMA * base
    Lw = max(float(np.percentile(Y, 99.95)), 1.0)
    out = np.empty(full.shape, np.uint16)
    for y0 in range(0, full.shape[0], STRIP):
        lin = to_srgb_linear(full[y0:y0 + STRIP], fr) * base
        Yl = lin @ LUMA
        lin *= ((1 + Yl / Lw ** 2) / (1 + Yl))[..., None]
        out[y0:y0 + STRIP] = (gamma(lin) * 65535 + 0.5).astype(np.uint16)
    return orient(out, fr.flip)


def merge_set(paths, out_path, tiff=False, progress=lambda f, s: None):
    """Merge one bracket set of RAW files into out_path (JPEG) and, optionally, a 16-bit TIFF next to it."""
    t0 = time.time()
    frames = []
    for i, p in enumerate(paths):
        frames.append(load_raw(p))
        progress(0.05 * (i + 1) / len(paths), "Reading")
    img, full, base, ref, info = merge_frames(frames, lambda f, s: progress(0.05 + 0.95 * f, s))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    save_jpeg(img, out_path, frames[ref])
    del img
    if tiff:
        save_tiff16(tiff_image(full, base, frames[ref]), os.path.splitext(out_path)[0] + ".tif")
    info["seconds"] = round(time.time() - t0, 1)
    progress(1.0, "Done")
    return info


# ---------------------------------------------------------------- self-test (synthetic frames)

def synthetic_set(seed=0, H=1200, W=1800, shift=(3.4, -2.2)):
    """Three Bayer frames (-2, 0, +2 EV) of a high-contrast scene with real-looking noise and clipping;
    the +2 EV frame is shifted. Returns (frames, true linear scene in camera RGB at the 0 EV exposure)."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:H, 0:W].astype(f32)
    scene = 0.02 + 0.05 * (np.sin(xx / 9) > 0) * (np.cos(yy / 13) > 0)       # dark textured room
    scene = scene + 3.0 * ((xx > W * 0.65) & (yy < H * 0.4))                  # bright window
    scene = scene + 0.2 * np.exp(-((xx - W * 0.3) ** 2 + (yy - H * 0.6) ** 2) / (2 * 40 ** 2))
    scene = np.stack([scene, scene * 0.9, scene * 0.7], -1).astype(f32)
    black, white = 512.0, 16380.0
    frames = []
    for bias, shift_this in ((0, (0, 0)), (-2, (0, 0)), (2, shift)):
        k = 2.0 ** bias
        sc = scene if shift_this == (0, 0) else warp(scene, mapping(np.eye(2), np.array(shift_this, f32)))
        lin = sc * k
        noisy = lin + rng.normal(0, 1, lin.shape).astype(f32) * np.sqrt(4e-4 * np.clip(lin, 0, None) + 2e-6)
        dn = np.clip(noisy, 0, None) * (white - black) + black
        dn = np.clip(dn, 0, white).astype(np.uint16)
        bayer = np.empty((H, W), np.uint16)
        bayer[0::2, 0::2] = dn[0::2, 0::2, 0]
        bayer[0::2, 1::2] = dn[0::2, 1::2, 1]
        bayer[1::2, 0::2] = dn[1::2, 0::2, 1]
        bayer[1::2, 1::2] = dn[1::2, 1::2, 2]
        half, satc, g1, g2 = half_from_bayer(bayer, [[0, 1], [3, 2]], "RGBG", [black] * 4, white)
        full = ((dn.astype(f32) - black) * 4).clip(0, 65535).astype(np.uint16)
        fr = Frame(f"F{bias:+d}.ARW", half, satc, g1, g2, full, 1 / (4 * (white - black)),
                   (1 / 100) * k, float(bias), np.ones(3, f32), np.eye(3, dtype=f32))
        frames.append(fr)
    return frames, scene


def selftest():
    frames, scene = synthetic_set()
    fr = frames[int(np.argmin([abs(f.bias) for f in frames]))]
    single = fr.full.astype(f32) * fr.full_scale
    img, merged, base, ref, info = merge_frames(frames)
    m = (slice(40, -40), slice(40, -40))
    dark = (scene[..., 1] < 0.03)[m]
    err_merged = np.abs(merged[m] - scene[m])[dark].mean()
    err_single = np.abs(single[m] - scene[m])[dark].mean()
    shift = next(f for f in info["frames"] if f["name"] == "F+2.ARW")["shift_px"]
    win = (scene[..., 1] > 2)[m]
    problems = []
    if not (abs(shift[0] + 3.4) < 0.3 and abs(shift[1] - 2.2) < 0.3):  # the frame was moved by (+3.4, -2.2)
        problems.append(f"alignment found {shift}, expected [-3.4, 2.2]")
    if not err_merged < 0.6 * err_single:
        problems.append(f"shadows not cleaner: merged error {err_merged:.4g} vs single {err_single:.4g}")
    if not abs(merged[m][win].mean() / scene[m][win].mean() - 1) < 0.05:
        problems.append("window brightness not recovered from the dark frame")
    if img.dtype != np.uint8 or img.shape != scene.shape:
        problems.append("bad output image")
    return problems, info


def main(argv):
    if argv[:1] == ["selftest"]:
        problems, info = selftest()
        print("\n".join(problems) or "PASS")
        return 1 if problems else 0
    if argv[:1] == ["merge"] and len(argv) >= 4:
        tiff = "--tiff" in argv
        args = [a for a in argv[1:] if a != "--tiff"]
        out_dir, files = args[0], args[1:]
        out = os.path.join(out_dir, _engine().hdr_name([os.path.basename(f) for f in files]))
        info = merge_set(files, out, tiff=tiff,
                         progress=lambda f, s: print(f"\r{s:13} {f * 100:5.1f}%", end="", flush=True))
        print(f"\nSaved {out}")
        import json
        print(json.dumps(info, indent=1))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
