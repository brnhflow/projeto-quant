"""Build an HTML report for the example portfolio with synthetic market data.

Run: uv run python scripts/demo_report.py  ->  reports/demo.html

The prices and FX rates are simulated (seeded random walks), so the numbers mean nothing;
the point is to exercise the real pipeline end to end:
holdings CSV -> align calendars -> convert to EUR -> portfolio value and returns.
"""

from __future__ import annotations

import html
import json
from datetime import date
from itertools import pairwise
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd

from quant.align import align_to_dates
from quant.fx import to_base_currency
from quant.holdings import load_holdings
from quant.returns import portfolio_value

ROOT = Path(__file__).parents[1]
OUT = ROOT / "reports" / "demo.html"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
SERIES_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]


# ---------------------------------------------------------------- synthetic data


def _walk(rng: np.random.Generator, dates: pd.DatetimeIndex, start: float, vol: float) -> pd.Series:
    """Geometric random walk: daily log-returns ~ Normal(0, vol)."""
    steps: npt.NDArray[np.float64] = rng.normal(0.0, vol, len(dates))
    steps[0] = 0.0
    return pd.Series(start * np.exp(steps.cumsum()), index=dates)


def synthetic_market() -> tuple[pd.DataFrame, pd.DataFrame, pd.DatetimeIndex]:
    """Prices on each market's own calendar, FX on ECB-like days, and the target calendar."""
    rng = np.random.default_rng(7)
    weekdays = pd.bdate_range("2025-11-24", "2026-11-20")
    carnival = pd.to_datetime(["2026-02-16", "2026-02-17"])
    b3_days = weekdays.difference(carnival)
    every_day = pd.date_range(weekdays[0], weekdays[-1], freq="D")

    prices = pd.concat(
        {
            "PETR4": _walk(rng, b3_days, 38.0, 0.018),
            "VALE3": _walk(rng, b3_days, 61.0, 0.017),
            "ASML": _walk(rng, weekdays, 650.0, 0.022),
            "IWDA": _walk(rng, weekdays, 95.0, 0.009),
            "BTC": _walk(rng, every_day, 90_000.0, 0.03),
        },
        axis="columns",
        sort=True,
    )
    fx = pd.concat(
        {"BRL": _walk(rng, weekdays, 0.165, 0.007), "USD": _walk(rng, weekdays, 0.92, 0.004)},
        axis="columns",
    )
    return prices, fx, weekdays


# ---------------------------------------------------------------- formatting


def eur(x: float, decimals: int = 0) -> str:
    """Format as euros, Portuguese style: 1.234,56 €."""
    text = f"{x:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{text} €"


def num(x: float, decimals: int = 2) -> str:
    """Format a number Portuguese style: 1.234,56."""
    return f"{x:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


MONTHS = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def pct(x: float) -> str:
    """Format a decimal as a signed percentage with one decimal."""
    return f"{x * 100:+.1f}%".replace(".", ",")


def nice_ticks(lo: float, hi: float, count: int = 4) -> list[float]:
    """Round axis ticks covering [lo, hi]."""
    raw = (hi - lo) / count
    magnitude = 10 ** np.floor(np.log10(raw))
    step = min((m * magnitude for m in (1, 2, 2.5, 5, 10)), key=lambda s: abs(s - raw))
    first = np.floor(lo / step) * step
    return [float(first + i * step) for i in range(int(np.ceil((hi - first) / step)) + 1)]


# ---------------------------------------------------------------- charts (inline SVG)


def line_chart(chart_id: str, series: dict[str, pd.Series], y_label: str, kind: str) -> str:
    """SVG line chart sharing one x axis (dates) and one y axis, with crosshair data."""
    w, h, left, right, top, bottom = 760, 280, 64, 96, 16, 32
    index = next(iter(series.values())).index
    lo = min(float(s.min()) for s in series.values())
    hi = max(float(s.max()) for s in series.values())
    ticks = nice_ticks(lo, hi)
    y0, y1 = ticks[0], ticks[-1]

    def x(i: int) -> float:
        return left + i * (w - left - right) / (len(index) - 1)

    def y(v: float) -> float:
        return top + (y1 - v) * (h - top - bottom) / (y1 - y0)

    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" id="{chart_id}" role="img">']
    for t in ticks:
        label = eur(t) if kind == "eur" else f"{t:.0f}"
        parts.append(
            f'<line class="grid" x1="{left}" x2="{w - right}" y1="{y(t):.1f}" y2="{y(t):.1f}"/>'
            f'<text class="tick" x="{left - 8}" y="{y(t) + 4:.1f}" text-anchor="end">{label}</text>'
        )
    month_starts = [i for i in range(1, len(index)) if index[i].month != index[i - 1].month]
    for i in month_starts[::2]:
        parts.append(
            f'<text class="tick" x="{x(i):.1f}" y="{h - 10}" text-anchor="middle">'
            f"{MONTHS[index[i].month - 1]} {index[i]:%y}</text>"
        )
    label_y = {name: y(float(s.iloc[-1])) + 4 for name, s in series.items()}
    ordered = sorted(label_y, key=lambda n: label_y[n])
    for prev, cur in pairwise(ordered):
        label_y[cur] = max(label_y[cur], label_y[prev] + 15)  # keep labels 15px apart
    for k, (name, s) in enumerate(series.items()):
        d = " ".join(
            f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(float(v)):.1f}" for i, v in enumerate(s)
        )
        parts.append(f'<path class="line s{k}" d="{d}"/>')
        if len(series) > 1:
            parts.append(
                f'<text class="direct s{k}-text" x="{w - right + 8}" y="{label_y[name]:.1f}">'
                f"{html.escape(name)}</text>"
            )
    parts.append(
        f'<line class="cross" x1="0" x2="0" y1="{top}" y2="{h - bottom}" visibility="hidden"/>'
    )
    parts.append(
        f'<rect class="hit" x="{left}" y="{top}" width="{w - left - right}" height="{h - top - bottom}"/>'
    )
    parts.append("</svg>")
    data = {
        "dates": [d.strftime("%d/%m/%Y") for d in index],
        "series": {name: [round(float(v), 4) for v in s] for name, s in series.items()},
        "kind": kind,
        "x0": left,
        "x1": w - left - right,
        "w": w,
    }
    script = f"<script>charts['{chart_id}'] = {json.dumps(data)};</script>"
    return f'<figure aria-label="{html.escape(y_label)}">{"".join(parts)}</figure>{script}'


def bar_chart(values: pd.Series) -> str:
    """Horizontal bars, largest first, labelled with value and share."""
    values = values.sort_values(ascending=False)
    total = float(values.sum())
    w, row, left, right = 760, 34, 72, 150
    h = row * len(values) + 8
    span = w - left - right
    top_value = float(values.iloc[0])
    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img">']
    for i, (name, v) in enumerate(values.items()):
        bw = max(span * float(v) / top_value, 6)
        yy = 4 + i * row
        parts.append(
            f'<g class="bar"><title>{html.escape(str(name))}: {eur(float(v))}</title>'
            f'<text class="label" x="{left - 10}" y="{yy + 18}" text-anchor="end">{html.escape(str(name))}</text>'
            f'<rect class="s0-fill" x="{left}" y="{yy + 4}" width="{bw:.1f}" height="20" rx="4"/>'
            f'<rect class="s0-fill" x="{left}" y="{yy + 4}" width="6" height="20"/>'
            f'<text class="value" x="{left + bw + 8:.1f}" y="{yy + 18}">'
            f"{eur(float(v))} · {float(v) / total * 100:.0f}%".replace(".", ",", 1)
            + "</text></g>"
        )
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------- report


def build() -> str:
    """Run the pipeline on synthetic data and return the report HTML."""
    holdings = load_holdings(ROOT / "data" / "holdings.example.csv")
    raw_prices, raw_fx, calendar = synthetic_market()

    local = align_to_dates(raw_prices, calendar)
    fx = align_to_dates(raw_fx, calendar)
    in_eur = to_base_currency(local, holdings["currency"], fx)
    value = portfolio_value(in_eur, holdings["quantity"]).dropna()

    last = in_eur.iloc[-1]
    position_eur = last[holdings.index] * holdings["quantity"]
    total_return = float(value.iloc[-1] / value.iloc[0] - 1)

    petr_brl = local["PETR4"] / local["PETR4"].iloc[0] * 100
    petr_eur = in_eur["PETR4"] / in_eur["PETR4"].iloc[0] * 100
    fx_effect = float(petr_eur.iloc[-1] - petr_brl.iloc[-1]) / 100

    total_eur = float(position_eur.sum())
    quantity = {str(k): float(v) for k, v in holdings["quantity"].to_dict().items()}
    currency = {str(k): str(v) for k, v in holdings["currency"].to_dict().items()}
    local_last = {str(k): float(v) for k, v in local.iloc[-1].to_dict().items()}
    eur_last = {str(k): float(v) for k, v in last.to_dict().items()}
    worth = {str(k): float(v) for k, v in position_eur.to_dict().items()}
    rows = "".join(
        f"<tr><td>{html.escape(a)}</td><td>{num(quantity[a], 2).rstrip('0').rstrip(',')}</td>"
        f"<td>{currency[a]}</td><td class='num'>{num(local_last[a])}</td>"
        f"<td class='num'>{eur(eur_last[a], 2)}</td><td class='num'>{eur(worth[a])}</td>"
        f"<td class='num'>{num(worth[a] / total_eur * 100, 1)}%</td></tr>"
        for a in sorted(worth, key=lambda k: worth[k], reverse=True)
    )
    period = f"{value.index[0]:%d/%m/%Y} a {value.index[-1]:%d/%m/%Y}"

    return TEMPLATE.format(
        css=CSS,
        js=JS,
        period=period,
        generated=date.today().strftime("%d/%m/%Y"),
        value_now=eur(float(value.iloc[-1])),
        total_return=pct(total_return),
        days=len(value),
        largest=html.escape(str(position_eur.idxmax())),
        largest_share=f"{float(position_eur.max() / position_eur.sum()) * 100:.0f}%",
        chart_value=line_chart("value", {"Carteira": value}, "Valor da carteira em euros", "eur"),
        chart_mix=bar_chart(position_eur),
        chart_fx=line_chart(
            "fx", {"em reais": petr_brl, "em euros": petr_eur}, "PETR4, base 100", "index"
        ),
        fx_sentence=(
            f"Nesse período o câmbio {'somou' if fx_effect >= 0 else 'tirou'} "
            f"{num(abs(fx_effect) * 100, 1)} pontos ao resultado em euros."
        ),
        rows=rows,
    )


_CSS_TEMPLATE = """
:root{--surface:#fcfcfb;--page:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--grid:#e6e5e0;
--s0:__S0__;--s1:__S1__}
@media (prefers-color-scheme:dark){:root{--surface:#1a1a19;--page:#0d0d0d;--ink:#f0efec;
--ink2:#c3c2b7;--grid:#383835;--s0:__S0D__;--s1:__S1D__}}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);
font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:840px;margin:0 auto;padding:32px 20px 64px}
.banner{border:1px solid var(--grid);border-radius:8px;padding:10px 14px;color:var(--ink2);
font-size:13px;margin-bottom:24px}
h1{font-size:24px;margin:0 0 4px}h2{font-size:17px;margin:0 0 2px}
.sub{color:var(--ink2);margin:0 0 20px;font-size:14px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:28px}
.tile{background:var(--surface);border:1px solid var(--grid);border-radius:10px;padding:14px 16px}
.tile .k{color:var(--ink2);font-size:13px}.tile .v{font-size:24px;font-weight:600;
font-variant-numeric:tabular-nums}
section{background:var(--surface);border:1px solid var(--grid);border-radius:12px;
padding:18px 18px 10px;margin-bottom:20px;position:relative}
figure{margin:8px 0 0}.chart{width:100%;height:auto;display:block}
.grid{stroke:var(--grid);stroke-width:1}.tick{fill:var(--ink2);font-size:11px}
.label,.value,.direct{fill:var(--ink);font-size:12px}.value{fill:var(--ink2)}
.line{fill:none;stroke-width:2;stroke-linejoin:round}.s0{stroke:var(--s0)}.s1{stroke:var(--s1)}
.s0-fill{fill:var(--s0)}.cross{stroke:var(--ink2);stroke-width:1;stroke-dasharray:3 3}
.hit{fill:transparent;cursor:crosshair}
.tip{position:absolute;pointer-events:none;background:var(--surface);border:1px solid var(--grid);
border-radius:8px;padding:6px 10px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.12);display:none;
white-space:nowrap;font-variant-numeric:tabular-nums}
.legend{display:flex;gap:16px;font-size:13px;color:var(--ink2);margin-top:6px}
.legend i{display:inline-block;width:14px;height:3px;border-radius:2px;vertical-align:middle;margin-right:6px}
table{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}
th,td{padding:7px 8px;border-bottom:1px solid var(--grid);text-align:left}
th{color:var(--ink2);font-weight:500}.num{text-align:right}
.notes{color:var(--ink2);font-size:13px}.notes li{margin-bottom:4px}
"""
CSS = (
    _CSS_TEMPLATE.replace("__S0D__", SERIES_DARK[0])
    .replace("__S1D__", SERIES_DARK[1])
    .replace("__S0__", SERIES[0])
    .replace("__S1__", SERIES[1])
)

JS = """
const charts = {};
function fmt(kind, v){
  if(kind==='eur') return v.toLocaleString('pt-PT',{maximumFractionDigits:0})+' €';
  return v.toLocaleString('pt-PT',{maximumFractionDigits:1});
}
window.addEventListener('DOMContentLoaded',()=>{
  for(const [id,d] of Object.entries(charts)){
    const svg=document.getElementById(id), sec=svg.closest('section');
    const cross=svg.querySelector('.cross'), hit=svg.querySelector('.hit');
    const tip=document.createElement('div'); tip.className='tip'; sec.appendChild(tip);
    const n=d.dates.length;
    hit.addEventListener('mousemove',e=>{
      const p=svg.createSVGPoint(); p.x=e.clientX; p.y=e.clientY;
      const loc=p.matrixTransform(svg.getScreenCTM().inverse());
      const i=Math.max(0,Math.min(n-1,Math.round((loc.x-d.x0)/d.x1*(n-1))));
      const xs=d.x0+i*d.x1/(n-1);
      cross.setAttribute('x1',xs); cross.setAttribute('x2',xs); cross.setAttribute('visibility','visible');
      let h='<b>'+d.dates[i]+'</b>';
      for(const [name,vals] of Object.entries(d.series)) h+='<br>'+name+': '+fmt(d.kind,vals[i]);
      tip.innerHTML=h; tip.style.display='block';
      const r=sec.getBoundingClientRect();
      let left=e.clientX-r.left+14; if(left>r.width-170) left-=190;
      tip.style.left=left+'px'; tip.style.top=(e.clientY-r.top-10)+'px';
    });
    hit.addEventListener('mouseleave',()=>{tip.style.display='none'; cross.setAttribute('visibility','hidden');});
  }
});
"""

TEMPLATE = """<!DOCTYPE html>
<html lang="pt"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Carteira de exemplo</title><style>{css}</style><script>{js}</script></head>
<body><main>
<div class="banner">Dados sintéticos: preços e câmbio são simulados. A carteira é o arquivo
de exemplo. O que é real aqui é o cálculo, o mesmo que vai rodar com os seus dados.</div>
<h1>Carteira de exemplo</h1>
<p class="sub">{period} · valores em euros · gerado em {generated}</p>
<div class="tiles">
  <div class="tile"><div class="k">Valor hoje</div><div class="v">{value_now}</div></div>
  <div class="tile"><div class="k">Retorno no período</div><div class="v">{total_return}</div></div>
  <div class="tile"><div class="k">Maior posição</div><div class="v">{largest} · {largest_share}</div></div>
  <div class="tile"><div class="k">Dias úteis analisados</div><div class="v">{days}</div></div>
</div>
<section><h2>Valor da carteira</h2>
<p class="sub">Quantidades fixas, preços convertidos pelo câmbio de cada dia.</p>{chart_value}</section>
<section><h2>Onde está o dinheiro</h2><p class="sub">Valor de cada posição hoje.</p>{chart_mix}</section>
<section><h2>O efeito do câmbio</h2>
<p class="sub">PETR4 em reais e em euros, os dois começando em 100. A distância entre as linhas
é o câmbio. {fx_sentence}</p>{chart_fx}
<div class="legend"><span><i style="background:var(--s0)"></i>em reais</span>
<span><i style="background:var(--s1)"></i>em euros</span></div></section>
<section><h2>Posições</h2>
<table><thead><tr><th>Ativo</th><th>Qtd.</th><th>Moeda</th><th class="num">Preço local</th>
<th class="num">Preço em €</th><th class="num">Valor em €</th><th class="num">Peso</th></tr></thead>
<tbody>{rows}</tbody></table></section>
<section class="notes"><h2>Premissas deste relatório</h2><ul>
<li>Quantidades fixas no período inteiro: sem compras, vendas, aportes ou resgates.</li>
<li>Calendário: dias úteis europeus. Num feriado da B3 (Carnaval), as ações brasileiras
valem o último fechamento; o bitcoin do fim de semana entra na segunda-feira.</li>
<li>Câmbio do mesmo dia do preço, nunca de um dia posterior.</li>
<li>Ainda não calculado: volatilidade, pior queda, risco por posição. Entram nas próximas etapas.</li>
</ul></section>
</main></body></html>
"""


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(build(), encoding="utf-8")
    print(f"wrote {OUT}")
