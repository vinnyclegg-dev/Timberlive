"""Text map of paths (=) and heights in an area. Usage: python pathmap.py x0 y0 w h"""
import sys, json
sys.path.insert(0, __import__("os").path.dirname(__file__))
import timberlive_mcp as t
x0,y0,w,h = [int(a) for a in sys.argv[1:5]]
m = t._call('GET','/api/map',params={'x':x0,'y':y0,'w':w,'h':h})
grid=[list(r) for r in m['objects']]
r=t.list_buildings('Path'); r=json.loads(r) if isinstance(r,str) else r
for b in (r['buildings'] if isinstance(r,dict) else r):
    if b['template'].startswith('Path') and x0<=b['x']<x0+w and y0<=b['y']<y0+h:
        grid[y0+h-1-b['y']][b['x']-x0]='='
print('x from',x0,'; top row y=',y0+h-1)
for i,row in enumerate(grid): print('%3d |%s|'%(y0+h-1-i,''.join(row)))
print(m['legend'])
