import importlib.util, json, sys, numpy as np
spec = importlib.util.spec_from_file_location("cal", "/home/claude/ION_MIVE/backend/scripts/h1/h1_ab_calibration.py")
cal = importlib.util.module_from_spec(spec); spec.loader.exec_module(cal)
D = "/mnt/project-files/voe-latency"
data = cal.load(f"{D}/e3/data/v04_pa/e3pa_ive_sizing.csv", f"{D}/h1/data/h1_ab_baseline.json", f"{D}/h1/data/h1_cap_sensitivity.json")
X = data["X"]
rng = np.random.default_rng(20261008)
keys = ("claims", "coverage", "uncertainty", "uncertainty_chars")
stack = np.stack([X[k] for k in keys], axis=2)
sets = {"current (0.5/0.05/0.25)": {"claims": 0.5, "coverage": 0.05, "uncertainty": 0.25},
        "N81 rec (0.5/0.05/0.40)": {"claims": 0.5, "coverage": 0.05, "uncertainty": 0.40},
        "N162 rec (0.35/0.03/0.30)": {"claims": 0.35, "coverage": 0.03, "uncertainty": 0.30}}
out = {}
for model in ("distinct", "pooled"):
    for per_q in (3, 6):
        A, B = cal.null_pairs(rng, stack, 4000, per_q, model)
        idx = cal.boot_index(rng, 2000)
        b = {k: cal.mean_ci(B[..., j] - A[..., j], idx)[1:] for j, k in enumerate(keys)}
        w1 = b["uncertainty"][1] < 0; w2 = b["uncertainty_chars"][1] < 0
        ua, ub = A[..., 2], B[..., 2]
        bo = ((ub == 0) & (ua > 0)).sum(axis=(1, 2)); ao = ((ua == 0) & (ub > 0)).sum(axis=(1, 2))
        w3 = np.array([x > y and cal.sign_test(int(x), int(y)) < 0.05 for x, y in zip(bo, ao)])
        warn = w1 | w2 | w3
        for name, m in sets.items():
            ni = np.ones(len(w1), bool)
            for k, mg in m.items():
                ni &= b[k][0] > -mg
            out[f"{model} N={27*per_q} {name}"] = {"all_three_NI": float(ni.mean()), "no_W1_W3": float((~warn).mean()),
                                                  "clean_count_endpoints": float((ni & ~warn).mean())}
for k, v in out.items():
    print(f"{k:45s} NI {v['all_three_NI']:.3f}  noW {v['no_W1_W3']:.3f}  clean {v['clean_count_endpoints']:.3f}")
json.dump(out, open("joint_v1.json", "x"), indent=1, sort_keys=True)
