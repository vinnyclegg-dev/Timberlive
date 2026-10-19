"""List plants standing on water tiles (they won't grow). Usage: python wetplants.py x,y,w,h"""
import re, sys, json
sys.path.insert(0, __import__('os').path.dirname(__file__))
import timberlive_mcp as t
PLANTS = ('Kohlrabi', 'Cassava', 'Pine', 'Oak', 'Birch', 'BlueberryBush', 'Maple', 'ChestnutTree', 'CoffeeBush')
def grid(txt, name):
    sec = txt.split(name, 1)[1]
    return [l for l in sec.split('\n')[1:] if l.startswith('|')][:0] or [l for l in sec.split('\n') if l.startswith('|')]
for x0, y0, w, h in [tuple(map(int, a.split(','))) for a in sys.argv[1:]]:
    txt = t.view_map(x0, y0, w, h)
    water = grid(txt.split('MOISTURE')[0], 'WATER')
    objs = grid(txt, 'OBJECTS:')
    leg = dict(re.findall(r'"(\w)":\s*"([\w.]+)"', txt.split('LEGEND:')[1]))
    top = y0 + h - 1
    bad = [(x0 + c, top - r, leg[o]) for r, (wl, ol) in enumerate(zip(water, objs))
           for c, (wc, o) in enumerate(zip(wl[1:-1], ol[1:-1])) if wc != ' ' and leg.get(o) in PLANTS]
    print(x0, y0, len(bad), bad[:20])
