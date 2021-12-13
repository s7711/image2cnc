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
print "Opening image: %s" % imgFileName
img = Image.open(imgFileName)

# image statistics

print "Image size: %d w, %d h" % img.size
print "Stock size: %.1fmm w/x, %.1fmm h/y" % (img.size[0]*px2mm,img.size[1]*px2mm)
print "Image mode: %s" % img.mode

# Convert to grey scale
img = img.convert("L")
print "Image range: %d min, %d max" % img.getextrema()

# Tool compensation
# Create a 3D numpy array. Axes 1,2 are x,y. Axis 3 is the image shifted (stacked 2D)
# Then find max along axis 3 to bring back to 2D
pxTool = int(math.floor(toolRadius / px2mm))      # Tool radius in pixels
numCols = 1+2*pxTool                              # pixel compensation width
print("Using {:d} pixels radius for the tool and {:d}x{:d} pixels search".format(pxTool, numCols, numCols))
print("Tool: {:s}".format(tool))

imgComp = np.zeros((img.size[1]+2*pxTool,img.size[0]+2*pxTool)) # Compensated image

for ox in range(numCols):
    for oy in range(numCols):
        sqRadius = ((ox-pxTool)**2 + (oy-pxTool)**2) * px2mm**2  # pixel distance (mm) from tool centre, squared

        if sqRadius < toolRadius**2:
            # Then inside the tool
            if tool == 'ball':
                dh = (toolRadius - math.sqrt( toolRadius**2 - sqRadius))
            else:
                dh = 0 # 'flat'
            imgTool = np.zeros((img.size[1]+2*pxTool,img.size[0]+2*pxTool))
            imgTool[ox:img.size[1]+ox, oy:img.size[0]+oy] = np.asarray(img) - dh/ deltaCut
            imgComp = np.maximum(imgComp,imgTool)

img = Image.fromarray(np.uint8(imgComp[pxTool:pxTool+img.size[1],pxTool:pxTool+img.size[0]]))

# Blur image
if blurRadius > 0.0:
    print "Blurring image with %d px (%.1f mm) blur radius" % (blurRadius, blurRadius*px2mm)
    img = img.filter(ImageFilter.GaussianBlur(radius = blurRadius))

img.save("img_compensated.jpg")

# Open the G code file
print "Gcode file: %s" % ncFileName
nc = open(ncFileName,"w")

zMin = -passCut                    # Minimum depth for this pass
thisDecimation = decimation
while zMin >= depthMin:                           # Multiple cuts per row
    if (zMin - passCut) < depthMin:              # Last height?
        thisDecimation = finalDecimation
    print "G code for depth: %.2f with y decimation %d" % (zMin,thisDecimation)
    nc.write("G0 Z%.2f\n" % safeHeight)           # Go to safe height
    for y in range(0,img.size[1],2*thisDecimation):   # Each row forward and back
        # Assume safe height already
        ## Forward direction
        nc.write("G0 X0 Y%.2f\n" % (y*px2mm,) )   # Go to X0 and Y for this row
        nc.write("G1 Z%.2f F%d\n" % ( cutDepth(img,0,y,zMin), plungeRate ) )
        lastF = plungeRate
        for x in range(1,img.size[0]):            # Each column
            nc.write( shorterG1( x*px2mm, y*px2mm, cutDepth(img,x,y,zMin), feedRate))
        nc.write( skippedG1 )                      # Flush last skipped
        skippedG1 = ""
        nc.write("G0 Z%.2f\n" % safeHeight)       # Go to safe height
        ## Backward direction
        y = y + thisDecimation
        if y > img.size[1]:
            break
        nc.write("G0 X%.2f Y%.2f\n" % ((img.size[0]-1)*px2mm,y*px2mm,) )   # Go to X and Y for this row
        nc.write("G1 Z%.2f F%d\n" % ( cutDepth(img,img.size[0]-1,y,zMin), plungeRate ) )
        lastF = plungeRate
        for x in range(1,img.size[0]):            # Each column
            x1 = img.size[0] - x - 1
            nc.write( shorterG1( x1*px2mm, y*px2mm, cutDepth(img,x1,y,zMin), feedRate))
        nc.write( skippedG1 )                      # Flush last skipped
        skippedG1 = ""
        nc.write("G0 Z%.2f\n" % safeHeight)       # Go to safe height
    zMin = zMin - passCut                         # min Z for next pass

nc.close()






