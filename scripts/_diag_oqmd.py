"""临时探测：OQMD 对掺杂分数成分与 host 查询的行为。"""
import httpx

URL = "https://oqmd.org/oqmdapi/formationenergy"
for comp in ["Pb0.94Ti0.06Te", "Ge0.93Ti0.01Bi0.06Te", "PbTe", "GeTe"]:
    try:
        r = httpx.get(URL, params={"composition": comp, "limit": 3}, timeout=30,
                      follow_redirects=True)
        r.raise_for_status()
        data = r.json()
        entries = (data.get("data") or []) if isinstance(data, dict) else []
        meta = data.get("meta") if isinstance(data, dict) else {}
        print(f"{comp} -> n={len(entries)} meta={meta}")
        if entries:
            e = entries[0]
            print("   first:", e.get("name"), "delta_e=", e.get("delta_e"),
                  "stability=", e.get("stability"), "bg=", e.get("band_gap"))
    except Exception as exc:
        print(comp, "ERROR:", exc)
