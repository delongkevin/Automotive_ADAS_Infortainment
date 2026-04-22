import time
import sys
import cv2
import os
from datetime import datetime

def connectCamera(): 
    # Look for camera
    for i in range(2):
        camera = cv2.VideoCapture(i)
        if camera.isOpened():
            return_value, image = camera.read()
            newImage = time.time()
            cv2.imwrite('.//images//CVADAS_'+str(i)+'_TimeStamp_'+str(newImage)+'.png',image)
    del(camera)
            
    
if __name__ == "__main__":
    try:
        if not os.path.exists('.//images'):
            os.makedirs('.//images')
        connectCamera()
        sys.exit(1)
        
    except Exception as err:
        sys.exit(2)
