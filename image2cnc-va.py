# This program generates G code from an image using the pixel intesity
# for the cutting depth
# It will cut one path per image row, so scale your image to modify
# the number of passes

from PIL import Image
from PIL import ImageFilter
import numpy as np
import math

########################################################################
# definitions, which ideally should come from the command line
imgFileName = "img.jpg"
ncFileName = "img.nc"

px2mm = 0.25        # Scales the image to mm
decimation = 4      # 1 for cut every line, 2 for cut every 2 lines, etc.
finalDecimation = 1 # Decimation for the final cut
whiteCut = 0.0      # Z of white (255) in mm
blackCut = -4.0     # Z of black (0) in mm
passCut = 2.0       # Maximum cut per pass in mm
stockToLeave = 0.3  # Leave this amount of stock apart from on the final pass
blurRadius = 0.0    # Pixels
toolRadius = 1.25   # mm
tool = 'ball'       # 'ball' or 'flat'


safeHeight = 1.0    # Safe height for G0 travel
feedRate = 2000      # Cutting rate for XY
plungeRate = 500    # Cutting rate for first Z travel

# derived constants
deltaCut = (whiteCut - blackCut) / 255.0
depthMin = min(whiteCut, blackCut)

# global variables
lastX = -100000     # Last G1 X position
lastY = -100000     # Last G1 Y position
lastZ = -100000     # Last G1 Z position
lastF = -100000     # Last G1 feed rate
skippedG1 = ""      # Skipped G1 command to reduce file size

########################################################################
# cutDepth - quick function to compute the cut depth for a pixel
def cutDepth(im,x,y,mz):
    # Depth for this pixel
    y1 = im.size[1]-y-1
    d = im.getpixel((x,y1)) * deltaCut + blackCut
    
    # Min depth for this cut
    if d < mz:
        d = mz
        
    return d

########################################################################
# shortG1 - only write parameters that have changed
def shortG1(X, Y, Z, F):
    global lastX, lastY, lastZ, lastF
    
    strX = "X%.2f " % X if X != lastX else ""
    strY = "Y%.2f " % Y if Y != lastY else ""
    strZ = "Z%.2f " % Z if Z != lastZ else ""
    strF = "F%d" % F if F != lastF else ""
    
    lastX = X
    lastY = Y
    lastZ = Z
    lastF = F
    
    return "G1 " + strX + strY + strZ + strF + "\n"

def shorterG1(X, Y, Z, F):
    global lastX, lastY, lastZ, lastF, skippedG1
    
    # Count how many changes there are
    changes = 0
    if X != lastX:
        strX = "X%.2f " % X
        changes = changes + 1
    else:
        strX = ""
    if Y != lastY:
        strY = "Y%.2f " % Y
        changes = changes + 1
    else:
        strY = ""
    if Z != lastZ:
        strZ = "Z%.2f " % Z
        changes = changes + 1
    else:
        strZ = ""
    if F != lastF:
        strF = "F%d" % F
        changes = changes + 1
    else:
        strF = ""
        
    if changes > 1:
        returnStr = skippedG1 + "G1 " + strX + strY + strZ + strF + "\n"
        skippedG1 = ""
    else:
        skippedG1 = "G1 " + strX + strY + strZ + strF + "\n"
        returnStr = ""
    
    lastX = X
    lastY = Y
    lastZ = Z
    lastF = F
    
    return returnStr


# Open the image
print("Opening image: %s" % imgFileName)
img = Image.open(imgFileName)

# image statistics

print("Image size: %d w, %d h" % img.size)
print("Stock size: %.1fmm w/x, %.1fmm h/y" % (img.size[0]*px2mm,img.size[1]*px2mm))
print("Image mode: %s" % img.mode)

# Convert to grey scale
img = img.convert("L")
print("Image range: %d min, %d max" % img.getextrema())

# Tool compensation
# Needs to do a search over the tool area
# Find size of square (in pixels) that contains the tool
pxTool = int(math.floor(toolRadius / px2mm))  # Tool radius in pixels
numCols = 1+2*pxTool                          # pixel compensation width
print("Using {:d} pixels radius for the tool and {:d}x{:d} pixels search".format(pxTool, numCols, numCols))
print("Tool: {:s}".format(tool))

# imgComp holds the pixels that will have the least material cut
# Starts by assuming that we will cut everything
# Then the np.minimum/np.maximum functions will change it
if whiteCut > blackCut:
    imgComp = np.zeros((img.size[1]+2*pxTool,img.size[0]+2*pxTool))
else:
    imgComp = np.ones((img.size[1]+2*pxTool,img.size[0]+2*pxTool))*255

# ox (offset x) and oy (offset y) are the offsets into our square search
# Note that the centre is not when ox=0 but when ox=pxTool
for ox in range(numCols):
    for oy in range(numCols):
        # Distance from tool centre, squared, in mm2
        sqRadius = ((ox-pxTool)**2 + (oy-pxTool)**2) * px2mm**2  

        # Some of the pixels in the square are not cut by the tool
        # Test to see if the tool intersects this pixel
        if sqRadius < toolRadius**2:
            # Then inside the tool
            if tool == 'ball':
                # For ball tools we can cut higher when further
                # away from the centre
                dh = (toolRadius - math.sqrt( toolRadius**2 - sqRadius))
            
            else:
                # Flat tools have not height change
                dh = 0 # 'flat'
            
            # Could have a "V" tool shape here too, would need options
            # for the angle of the "V"
            
            # Note the "-dh/deltaCut" below, the same sign for both
            # because deltaCut changes sign
            if whiteCut > blackCut:
                imgTool = np.zeros((img.size[1]+2*pxTool,img.size[0]+2*pxTool))
                imgTool[ox:img.size[1]+ox, oy:img.size[0]+oy] = np.asarray(img) - dh/deltaCut
                imgComp = np.maximum(imgComp,imgTool)
            else:
                imgTool = np.ones((img.size[1]+2*pxTool,img.size[0]+2*pxTool))*255
                imgTool[ox:img.size[1]+ox, oy:img.size[0]+oy] = np.asarray(img) - dh/deltaCut
                imgComp = np.minimum(imgComp,imgTool)

# Back from np to PIL
img = Image.fromarray(np.uint8(imgComp[pxTool:pxTool+img.size[1],pxTool:pxTool+img.size[0]]))

# Blur image
if blurRadius > 0.0:
    print("Blurring image with %d px (%.1f mm) blur radius" % (blurRadius, blurRadius*px2mm))
    img = img.filter(ImageFilter.GaussianBlur(radius = blurRadius))

img.save("img_compensated.jpg")

# Open the G code file
print("Gcode file: %s" % ncFileName)
nc = open(ncFileName,"w")

# Write useful comment information
nc.write(";Created by image2cnc.py\n")
nc.write(";Millimetres per pixel: %.2f\n" % px2mm )
nc.write(";Decimation for normal lines: %d\n" % decimation )
nc.write(";Decimation for final cut: %d\n" % finalDecimation )
nc.write(";Stock to leave apart from final pass: %.2f\n" % stockToLeave)
nc.write(";Safe height: %.2f\n" % safeHeight )
nc.write(";White cut depth: %.2f\n" % whiteCut )
nc.write(";Black cut depth: %.2f\n" % blackCut )
nc.write(";Maximum pass cut depth: %.2f\n" % passCut )
nc.write(";Tool radius (diameter): %.3f (%.3f)\n" % (toolRadius, toolRadius*2.0))
nc.write(";Tool type: %s\n" % tool )
nc.write(";Feed rate: %.0f\n" % feedRate )
nc.write(";Plunge rate: %.0f\n" % plungeRate )
nc.write(";Image size: %d w, %d h\n" % img.size)
nc.write(";Stock size: %.1fmm w/x, %.1fmm h/y\n" % (img.size[0]*px2mm,img.size[1]*px2mm))
nc.write(";Image range: %d min, %d max\n" % img.getextrema())
nc.write(";Using {:d} pixels radius for the tool and {:d}x{:d} pixels search\n".format(pxTool, numCols, numCols))

zMin = -passCut                    # Minimum depth for this pass
thisDecimation = decimation
addZ = stockToLeave                # Add to Z apart from final cut
while True:                        # Multiple cuts per row
    if (zMin - passCut) < depthMin:              # Last height?
        thisDecimation = finalDecimation
        addZ = 0.0
    print("G code for depth: %.2f with y decimation %d" % (zMin,thisDecimation))
    nc.write("\n;G code for depth: %.2f with y decimation %d\n" % (zMin,thisDecimation))
    nc.write("G0 Z%.2f\n" % safeHeight)           # Go to safe height
    for y in range(0,img.size[1],2*thisDecimation):   # Each row forward and back
        # Assume safe height already
        ## Forward direction
        nc.write("G0 X0.00 Y%.2f\n" % (y*px2mm,) )   # Go to X0 and Y for this row
        nc.write("G1 Z%.2f F%d\n" % ( cutDepth(img,0,y,zMin)+addZ, plungeRate ) )
        lastF = plungeRate
        for x in range(1,img.size[0]):            # Each column
            nc.write( shorterG1( x*px2mm, y*px2mm, cutDepth(img,x,y,zMin)+addZ, feedRate))
        nc.write( skippedG1 )                      # Flush last skipped
        skippedG1 = ""
        nc.write("G0 Z%.2f\n" % safeHeight)       # Go to safe height
        ## Backward direction
        y = y + thisDecimation
        if y > img.size[1]:
            break
        nc.write("G0 X%.2f Y%.2f\n" % ((img.size[0]-1)*px2mm,y*px2mm,) )   # Go to X and Y for this row
        nc.write("G1 Z%.2f F%d\n" % ( cutDepth(img,img.size[0]-1,y,zMin)+addZ, plungeRate ) )
        lastF = plungeRate
        for x in range(1,img.size[0]):            # Each column
            x1 = img.size[0] - x - 1
            nc.write( shorterG1( x1*px2mm, y*px2mm, cutDepth(img,x1,y,zMin)+addZ, feedRate))
        nc.write( skippedG1 )                      # Flush last skipped
        skippedG1 = ""
        nc.write("G0 Z%.2f\n" % safeHeight)       # Go to safe height
    
    if zMin == depthMin: break
    zMin = zMin - passCut                         # min Z for next pass
    if zMin < depthMin:
        zMin = depthMin
        thisDecimation = finalDecimation
        addZ = 0.0       

nc.close()






