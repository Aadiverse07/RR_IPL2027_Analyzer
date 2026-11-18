"""Dependency-free SVG calibration charts from the saved decile table."""
from pathlib import Path
import csv,html

ROOT=Path(__file__).resolve().parents[2]
IN=ROOT/'reports/phase_2/calibration_deciles.csv'
OUT=ROOT/'reports/phase_2/calibration_plots'

def render(rows,name,title):
    width,height=480,400;left,top,right,bottom=64,50,28,62
    pw,ph=width-left-right,height-top-bottom
    def x(v):return left+float(v)*pw
    def y(v):return top+(1-float(v))*ph
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',f'<text x="{width/2}" y="27" text-anchor="middle" font-family="Arial" font-size="15">{html.escape(title)}</text>']
    for t in [0,.2,.4,.6,.8,1]:
        parts.append(f'<line x1="{x(t)}" y1="{top}" x2="{x(t)}" y2="{top+ph}" stroke="#e5e7eb"/>')
        parts.append(f'<line x1="{left}" y1="{y(t)}" x2="{left+pw}" y2="{y(t)}" stroke="#e5e7eb"/>')
        parts.append(f'<text x="{x(t)}" y="{top+ph+20}" text-anchor="middle" font-family="Arial" font-size="10">{t:.1f}</text>')
        parts.append(f'<text x="{left-9}" y="{y(t)+3}" text-anchor="end" font-family="Arial" font-size="10">{t:.1f}</text>')
    parts.append(f'<line x1="{x(0)}" y1="{y(0)}" x2="{x(1)}" y2="{y(1)}" stroke="#9ca3af" stroke-dasharray="5 4"/>')
    pts=[]
    for r in rows:
        px=x(r['mean_predicted']);py=y(r['observed_win_rate']);pts.append(f'{px:.2f},{py:.2f}')
        parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="4" fill="#2563eb"><title>Decile {r["decile"]}; n={r["n"]}; predicted={float(r["mean_predicted"]):.3f}; observed={float(r["observed_win_rate"]):.3f}</title></circle>')
    if pts:parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#2563eb" stroke-width="2"/>')
    parts += [f'<text x="{left+pw/2}" y="{height-15}" text-anchor="middle" font-family="Arial" font-size="11">Mean predicted win probability</text>',
        f'<text x="17" y="{top+ph/2}" text-anchor="middle" transform="rotate(-90 17 {top+ph/2})" font-family="Arial" font-size="11">Observed win rate</text>','</svg>']
    (OUT/name).write_text('\n'.join(parts)+'\n',encoding='utf-8')

def build():
    OUT.mkdir(parents=True,exist_ok=True)
    with IN.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    groups=sorted({(r['format'],r['phase']) for r in rows if r['format']!='ALL'})
    overall=[r for r in rows if r['format']=='ALL' and r['phase']=='ALL']
    render(overall,'overall.svg','Chase model calibration — all eligible OOF states')
    for fmt,phase in groups:
        subset=[r for r in rows if r['format']==fmt and r['phase']==phase]
        render(subset,f'{fmt.lower()}_{phase}.svg',f'{fmt} · {phase} calibration')
    print(f'calibration SVG charts generated: {1+len(groups)}')

if __name__=='__main__':build()
