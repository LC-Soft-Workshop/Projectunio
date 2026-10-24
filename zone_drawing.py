"""Recover a convex four-corner zone from clicks made in any order."""
def ordered_quad(points):
    points=sorted(set(tuple(p) for p in points))
    if len(points)!=4:return None
    def cross(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def half(values):
        result=[]
        for p in values:
            while len(result)>1 and cross(result[-2],result[-1],p)<=0:result.pop()
            result.append(p)
        return result
    hull=half(points)[:-1]+half(reversed(points))[:-1]
    if len(hull)!=4:return None
    start=min(range(4),key=lambda i:hull[i][0]+hull[i][1])
    return [list(p) for p in hull[start:]+hull[:start]]
