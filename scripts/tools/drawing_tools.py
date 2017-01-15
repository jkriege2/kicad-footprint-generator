#!/usr/bin/env python

import sys
import os
import math
import time

# ensure that the kicad-footprint-generator directory is available
# sys.path.append(os.environ.get('KIFOOTPRINTGENERATOR'))  # enable package import from parent directory
# sys.path.append("D:\hardware\KiCAD\kicad-footprint-generator")  # enable package import from parent directory
sys.path.append(os.path.join(sys.path[0], "..", "..", "kicad_mod"))  # load kicad_mod path
sys.path.append(os.path.join(sys.path[0], "..", ".."))  # load kicad_mod path

from KicadModTree import *  # NOQA
from footprint_global_properties import *

# round for grid g
def roundG(x, g):
    if (x > 0):
        return math.ceil(x / g) * g
    else:
        return math.floor(x / g) * g


# round for courtyard grid
def roundCrt(x):
    return roundG(x, grid_crt)


# float-variant of range()
def frange(x, y, jump):
    while x < y:
        yield x
        x += jump


# inclusice float-variant of range()
def frangei(x, y, jump):
    while x <= y:
        yield x
        x += jump


# returns a list with a single rectangle around x,y with width and height w and h
def addKeepoutRect(x, y, w, h):
    return [[x - w / 2, x + w / 2, y - h / 2, y + h / 2]]


# returns a series of rectangle that lie around the circular pad around (x,y) with radius w=h
# if w!=h, addKeepoutRect() is called
def addKeepoutRound(x, y, w, h):
    if w != h:
        return addKeepoutRect(x, y, w, h)
    else:
        res = []
        Nrects = 4
        r = max(h, w) / 2
        yysum = 0
        for ya in frange(0, r, r / Nrects):
            a = math.fabs(math.asin(ya / r) / math.pi * 180)
            yy = math.fabs(r * math.sin(a / 180.0 * math.pi))
            xx = math.fabs(r * math.cos(a / 180.0 * math.pi))
            if (xx > 0):
                res.append([x - xx - 0.015, x + xx + 0.015, y - yy - r / Nrects - 0.015, y - yy + .015])
                res.append([x - xx - 0.015, x + xx + 0.015, y + yy - 0.015, y + yy + r / Nrects + 0.015])
            yysum = yysum + yy
        return res

# internal method for keepout-processing
def applyKeepouts(lines_in, y, xi, yi, keepouts):
    # print("  applyKeepouts(\n  lines_in=", lines_in, "  \n  y=", y, "   \n  xi=", xi, "   yi=", yi, "   \n  keepouts=", keepouts, ")")
    lines = lines_in
    changes = True
    while (changes):
        changes = False
        for ko in keepouts:
            ko = [min(ko[0], ko[1]), max(ko[0], ko[1]), min(ko[2], ko[3]), max(ko[2], ko[3])]
            if (ko[yi + 0] <= y) and (y <= ko[yi + 1]):
                # print("    INY: koy=", [ko[yi + 0], ko[yi + 1]], "  y=", y, "):             kox=", [ko[xi + 0], ko[xi + 1]])
                for li in reversed(range(0, len(lines))):
                    l = lines[li]
                    if (l[0] >= ko[xi + 0]) and (l[0] <= ko[xi + 1]) and (l[1] >= ko[xi + 0]) and (
                                l[1] <= ko[xi + 1]):  # Line completely inside -> remove
                        lines.pop(li)
                        # print("      H1: ko=", [ko[xi+0],ko[xi+1]], "  li=", li, "   l=", l, ")")
                        changes = True
                    elif (l[0] >= ko[xi + 0]) and (l[0] <= ko[xi + 1]) and (
                                l[1] > ko[
                                    xi + 1]):  # Line starts inside, but ends outside -> remove and add shortened
                        lines.pop(li)
                        lines.append([ko[xi + 1], l[1]])
                        # print("      H2: ko=", [ko[xi+0],ko[xi+1]], "  li=", li, "   l=", l, "): ", [ko[xi+1], l[1]])
                        changes = True
                    elif (l[0] < ko[xi + 0]) and (l[1] <= ko[xi + 1]) and (
                                l[1] >= ko[
                                    xi + 0]):  # Line starts outside, but ends inside -> remove and add shortened
                        lines.pop(li)
                        lines.append([l[0], ko[xi + 0]])
                        # print("      H3: ko=", [ko[xi+0],ko[xi+1]], "  li=", li, "   l=", l, "): ", [l[0], ko[xi+0]])
                        changes = True
                    elif (l[0] < ko[xi + 0]) and (
                                l[1] > ko[
                                    xi + 1]):  # Line starts outside, and ends outside -> remove and add 2 shortened
                        lines.pop(li)
                        lines.append([l[0], ko[xi + 0]])
                        lines.append([ko[xi + 1], l[1]])
                        # print("      H4: ko=", [ko[xi+0],ko[xi+1]], "  li=", li, "   l=", l, "): ", [l[0], ko[xi+0]], [ko[xi+1], l[1]])
                        changes = True
                        # else:
                        # print("      USE: ko=", [ko[xi+0],ko[xi+1]], "  li=", li, "   l=", l, "): ")
        if changes:
            break

    return lines

# gives True if the given point (x,y) is contained in any keepout
def containedInAnyKeepout(x,y, keepouts):
    for ko in keepouts:
        ko = [min(ko[0], ko[1]), max(ko[0], ko[1]), min(ko[2], ko[3]), max(ko[2], ko[3])]
        if x>=ko[0] and x<=ko[1] and y>=ko[2] and y<=ko[3]:
            #print("HIT!")
            return True
    #print("NO HIT ",x,y)
    return False

# draws the keepouts
def debug_draw_keepouts(kicad_modg, keepouts):
    for ko in keepouts:
        kicad_modg.append(RectLine(start=[ko[0],ko[2]],
                                  end=[ko[1],ko[3]],
                                  layer='F.Mask', width=0.01))
        
# split a vertical line so it does not interfere with keepout areas defined as [[x0,x1,y0,y1], ...]
def addHLineWithKeepout(kicad_mod, x0, x1, y, layer, width, keepouts=[], roun=0.001):
    # print("addHLineWithKeepout",y)
    linesout = applyKeepouts([[min(x0, x1), max(x0, x1)]], y, 0, 2, keepouts)
    for l in linesout:
        kicad_mod.append(
            Line(start=[roundG(l[0], roun), roundG(y, roun)], end=[roundG(l[1], roun), roundG(y, roun)], layer=layer,width=width))



# split a vertical line so it does not interfere with keepout areas defined as [[x0,x1,y0,y1], ...]
def addVLineWithKeepout(kicad_mod, x, y0, y1, layer, width, keepouts=[], roun=0.001):
    # print("addVLineWithKeepout",x)
    linesout = applyKeepouts([[min(y0, y1), max(y0, y1)]], x, 2, 0, keepouts)
    for l in linesout:
        kicad_mod.append(
            Line(start=[roundG(x, roun), roundG(l[0], roun)], end=[roundG(x, roun), roundG(l[1], roun)], layer=layer,
                 width=width))


# split a rectangle so it does not interfere with keepout areas defined as [[x0,x1,y0,y1], ...]
def addRectWithKeepout(kicad_mod, x, y, w, h, layer, width, keepouts=[], roun=0.001):
    addHLineWithKeepout(kicad_mod, x, x+w, y, layer,width,keepouts,roun)
    addHLineWithKeepout(kicad_mod, x, x + w, y+h, layer, width, keepouts, roun)
    addVLineWithKeepout(kicad_mod, x, y, y+h, layer, width, keepouts, roun)
    addVLineWithKeepout(kicad_mod, x+w, y, y + h, layer, width, keepouts, roun)

# split a plus sign so it does not interfere with keepout areas defined as [[x0,x1,y0,y1], ...]
def addPlusWithKeepout(km, x, y, w, h, layer, width, keepouts=[], roun=0.001):
    addHLineWithKeepout(km, x, x+w, y+h/2, layer,width,keepouts,roun)
    addVLineWithKeepout(km, x+w/2, y, y+h, layer, width, keepouts, roun)

# draw a rectangle with bevel on all sides (e.g. for crystals), or a simple rectangle if bevel_size0=0)
#
#   /----\
#  /      \
# |        |
# |        |
# |        |
# |        |
# |        |
#  \      /
#   \----/
def allBevelRect(model, x, size, layer, width, bevel_size=0.2):
    if bevel_size <= 0:
        model.append(RectLine(start=x, end=[x[0] + size[0], x[1] + size[1]], layer=layer, width=width))
    else:
        model.append(PolygoneLine(polygone=[[x[0] + bevel_size, x[1]],
                                            [x[0] + size[0] - bevel_size, x[1]],
                                            [x[0] + size[0], x[1] + bevel_size],
                                            [x[0] + size[0], x[1] + size[1] - bevel_size],
                                            [x[0] + size[0] - bevel_size, x[1] + size[1]],
                                            [x[0] + bevel_size, x[1] + size[1]],
                                            [x[0], x[1] + size[1] - bevel_size],
                                            [x[0], x[1] + bevel_size],
                                            [x[0] + bevel_size, x[1]]], layer=layer, width=width))

# draws a filled circle consisting of concentric circles of varying widths (e.g. for glue dots!)
def fillCircle(model, center, radius, layer, width):
    model.append(Circle(center=center, radius=radius, layer=layer, width=width))
    r = radius
    w = radius / 3
    r = radius - w / 2
    while r > w / 2:
        if r - 0.9 * w <= w / 2:
            model.append(Circle(center=center, radius=r, layer=layer, width=r * 2))
        else:
            model.append(Circle(center=center, radius=r, layer=layer, width=w))
        r = r - 0.9 * w



#     +------+
#    /       |
#   /        |
#   |        |
#   |        |
#   |        |
#   |        |
#   +--------+
#
#
def bevelRectTL(model, x, size, layer, width, bevel_size=1):
    model.append(PolygoneLine(
        polygone=[[x[0] + bevel_size, x[1]], [x[0] + size[0], x[1]], [x[0] + size[0], x[1] + size[1]],
                  [x[0], x[1] + size[1]], [x[0], x[1] + bevel_size], [x[0] + bevel_size, x[1]]], layer=layer,
        width=width))


#   +--------+
#   |        |
#   |        |
#   |        |
#   |        |
#   \        |
#    \       |
#     +------+
#
#
def bevelRectBL(model, x, size, layer, width, bevel_size=1):
    model.append(PolygoneLine(polygone=[[x[0], x[1]], [x[0] + size[0], x[1]], [x[0] + size[0], x[1] + size[1]],
                                        [x[0] + bevel_size, x[1] + size[1]], [x[0], x[1] + size[1] - bevel_size],
                                        [x[0], x[1]]], layer=layer, width=width))

# draws a DIP-package with half-circle at the top
#
# +----------+
# |   \  /   |
# |    ~~    |
# |          |
# |          |
# |          |
# |          |
# +----------+
def DIPRectT(model, x, size, layer, width, marker_size=2):
    model.append(PolygoneLine(
        polygone=[[x[0] + size[0] / 2 - marker_size / 2, x[1]], [x[0], x[1]], [x[0], x[1] + size[1]],
                  [x[0] + size[0], x[1] + size[1]], [x[0] + size[0], x[1]],
                  [x[0] + size[0] / 2 + marker_size / 2, x[1]]], layer=layer, width=width))
    model.append(Arc(center=[x[0] + size[0] / 2, x[1]], start=[x[0] + size[0] / 2 - marker_size / 2, x[1]], angle=-180,
                     layer=layer, width=width))


# draws a DIP-package with half-circle at the left
#
# +---------------+
# |-\             |
# |  |            |
# |-/             |
# +---------------+
def DIPRectL(model, x, size, layer, width, marker_size=2):
    model.append(PolygoneLine(polygone=[[x[0], x[1] + size[1] / 2 - marker_size / 2],
                                        [x[0], x[1]],
                                        [x[0] + size[0], x[1]],
                                        [x[0] + size[0], x[1] + size[1]],
                                        [x[0], x[1] + size[1]],
                                        [x[0], x[1] + size[1] / 2 + marker_size / 2]], layer=layer, width=width))
    model.append(Arc(center=[x[0], x[1] + size[1] / 2], start=[x[0], x[1] + size[1] / 2 - marker_size / 2], angle=180,
                     layer=layer, width=width))


# draws the left part of a DIP-package with half-circle at the left
#
# +--------
# |-\
# |  |
# |-/
# +--------
def DIPRectL_LeftOnly(model, x, size, layer, width, marker_size=2):
    model.append(Line(start=[x[0], x[1] + size[1] / 2 - marker_size / 2], end=[x[0], x[1]], layer=layer, width=width))
    model.append(
        Line(start=[x[0], x[1] + size[1]], end=[x[0], x[1] + size[1] / 2 + marker_size / 2], layer=layer, width=width))
    if size[0] > 0:
        model.append(Line(start=[x[0], x[1]], end=[x[0] + size[0], x[1]], layer=layer, width=width))
        model.append(Line(start=[x[0], x[1] + size[1]], end=[x[0] + size[0], x[1] + size[1]], layer=layer, width=width))
    
    model.append(Arc(center=[x[0], x[1] + size[1] / 2], start=[x[0], x[1] + size[1] / 2 - marker_size / 2], angle=180,
                     layer=layer, width=width))


# draws a THT quartz footprint (HC49) with a rect around it
#  +-------------------------+
#  |                         |
#  |   +----------------+    |
#  |  /                  \   |
#  |  \                  /   |
#  |   +----------------+    |
#  |                         |
#  +-------------------------+
def THTQuartzRect(model, x, size, inner_size, layer, width):
    model.append(RectLine(start=x, end=[x[0] + size[0], x[1] + size[1]], layer=layer, width=width))
    THTQuartz(model, [x[0] + (size[0] - inner_size[0]) / 2, x[1] + (size[1] - inner_size[1]) / 2], inner_size, layer,
              width)


# draws a THT quartz footprint (HC49)
#     +----------------+
#    /                  \
#    \                  /
#     +----------------+
def THTQuartz(model, x, size, layer, width):
    THTQuartzIncomplete(model, x, size, 180, layer, width)


# draws a THT quartz footprint (HC49)
#     +----------------+
#    /                  \
#    \                  /
#     +----------------+
def THTQuartzIncomplete(model, x, size, angle, layer, width):
    inner_size = size
    r = inner_size[1] / 2
    xtl = [x[0] + size[0] / 2 - (inner_size[0] / 2 - r), x[1] + size[1] / 2 - inner_size[1] / 2]
    xtr = [x[0] + size[0] / 2 + (inner_size[0] / 2 - r), x[1] + size[1] / 2 - inner_size[1] / 2]
    xbl = [x[0] + size[0] / 2 - (inner_size[0] / 2 - r), x[1] + size[1] / 2 + inner_size[1] / 2]
    xbr = [x[0] + size[0] / 2 + (inner_size[0] / 2 - r), x[1] + size[1] / 2 + inner_size[1] / 2]
    cl = [x[0] + size[0] / 2 - (inner_size[0] / 2 - r), x[1] + size[1] / 2]
    cr = [x[0] + size[0] / 2 + (inner_size[0] / 2 - r), x[1] + size[1] / 2]
    model.append(Line(start=xtl, end=xtr, layer=layer, width=width))
    model.append(Line(start=xbl, end=xbr, layer=layer, width=width))
    if angle >= 180:
        model.append(Arc(center=cl, start=xtl, angle=-angle, layer=layer, width=width))
        model.append(Arc(center=cr, start=xtr, angle=angle, layer=layer, width=width))
    else:
        model.append(Arc(center=cl, start=xtl, angle=-angle, layer=layer, width=width))
        model.append(Arc(center=cr, start=xtr, angle=angle, layer=layer, width=width))
        model.append(Arc(center=cl, start=xbl, angle=angle, layer=layer, width=width))
        model.append(Arc(center=cr, start=xbr, angle=-angle, layer=layer, width=width))
