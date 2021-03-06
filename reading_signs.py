#! /usr/bin/python

#-----------------------------------------------------------------------------------------------------------------------------------------------------------
# - finds blue rectangular markers by color tracking 
# - moves towards the object while keeping focus on the centre of the object
#   and adjusting motor speeds 
# - filters the white rectangle with the blak sign
# - adjust perspective and compare the sign with sign on the disk
# - displays centroid coordinates and camera range in window
#
# Hardware: Raspberry Pi B+ and Dagu Arduino mini driver board Remote controlled thru a W8+ desktop
# Software: Python 2.7, openCV, Numpy and Python classes of Dawn Robotics: http://www.dawnrobotics.co.uk/
#           raspberry_pi_camera_bot
#           raspberry_pi_camera_streamer
#           py_websockets_bot
#           
# Images are grabbed blocking (one by one). Using callback routines created memory problems on the Raspberry Pi
#
# Inspirational site for this script: http://roboticssamy.blogspot.nl/ Great Stuff !!
# A good example of object tracking by color can be found at http://www.roborealm.com/tutorial/color_object_tracking_2/slide010.php
# Very good instructions on openCV can be found at the site of Adrian Rosebrock: http://www.pyimagesearch.com 
# 
# Light quality is essential for object detection by color. Upfront calibrating the inRange values is essential
# This can be done by running calibrating_BGR_with_trackbars.py (can be imported as module when preferred)
# ToDo:
#     - complete evasion routine when obstacles are detected
#     - insert compass and encoder readings to log trajectory
#     - version with small camera images to run on the Raspberri Pi (without using websockets)
#-----------------------------------------------------------------------------------------------------------------------------------------------------------
import time
import argparse
import cv2
import numpy as np
import math 
import py_websockets_bot
import py_websockets_bot.mini_driver
import py_websockets_bot.robot_config
import random
import csv
# -------------------------------------------------------------------------------------
# Set and initialize variables
# -------------------------------------------------------------------------------------
b_low = 110                                                                           # BGR values (calibrate first)
g_low = 50                                                                            # Defaults:   
r_low = 50                                                                            # Low:  110,  50,  50
b_high = 130                                                                          # High: 130, 255, 255
g_high = 255                                                                          # At home:
r_high = 255                                                                          # Low:  110,  50,  85
lower_blue = np.array([b_low,g_low,r_low])                                            # High: 131, 119, 255
upper_blue = np.array([b_high,g_high,r_high])                                         #
font = cv2.FONT_HERSHEY_SIMPLEX
next_action = 'START'
marker_found = 0
centroid_x = 0
centroid_y = 0
w = 1
h = 0
area = 0
min_pan_angle = 70.0                                                                  # Limit swirling of neck
max_pan_angle = 110.0                                                                 #
max_width = 404 * 0.6                                                                 # factor to stop in time due to buffer/performance
max_range = 40                                                                        # Safety limit 
motor_speed = 40.0                                                                    # = 40%; corr. to PMW 44Hz
next_action = 'START'                                                                 # 
image = None
#-------------------------------------------------------------------------------------- grab camera image and track blue
def find_marker():
    global centroid_x, centroid_y, w, h, camera_range, marker_found, image
    marker_found = 0
    centroid_x = 0
    centroid_y = 0
    w = 1
    h = 0
    area = 0
    camera_range = 0
    image, _  = bot.get_latest_camera_image()
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)                                      # 0 - Set color space
    mask_image = cv2.inRange(hsv, lower_blue, upper_blue)                             # 1 - Mask only blue
    result_image = cv2.bitwise_and(image,image, mask= mask_image)                     # 2 - Convert masked color to white. Rest to black 
    result_image = cv2.cvtColor(result_image, cv2.COLOR_BGR2GRAY )                    # 3 - Convert to Gray (needed for binarizing)
    contours, _ = cv2.findContours(result_image,
                                   cv2.RETR_LIST,
                                   cv2.CHAIN_APPROX_SIMPLE)                           # 4 - Find contours of all shapes
    contours = sorted(contours, key=cv2.contourArea, reverse=True) [:1]               # 5 - Select biggest; drop the rest
    if len (contours) > 0:
        cnt = contours[0]
        x,y,w,h = cv2.boundingRect(cnt)
        centroid_x = x + (w/2)
        centroid_y = y + (h/2)
        camera_range = round((16175.288 / w),0)                                       # real width * focal length = 16175.288
        cv2.drawContours(image, [cnt], -1, (0, 0, 255), 2)                            # Not needed; Just to display the differance
        cv2.rectangle(image,(x,y),(x+w,y+h),(0,255,0),2)
        heads_up_display()
        cv2.imshow( "searching", image )
        cv2.waitKey(1)
        area = w * h
        if area > 2000:
            marker_found = 1
#-------------------------------------------------------------------------------------- Timer routine for accuracy
def time_out (milsec):
    for i in xrange (milsec):
        time.sleep (0.001)
#-------------------------------------------------------------------------------------- Display coordinates and range in window
def heads_up_display ():
    central = 'centre  %d : %d ' % (centroid_x, centroid_y)
    distance = 'range   %d ' % (camera_range)
    cv2.putText(image, central,(20, 25), font, 0.5,(0,255,0),2)
    cv2.putText(image, distance,(20, 45), font, 0.5,(0,255,0),2)
# -------------------------------------------------------------------------------------  
def read_sensors ():
    global sensor_data
    status_dict, _ = bot.get_robot_status_dict()
    sensor_dict = status_dict[ "sensors" ]
    sensor_data = sensor_dict[ "digital" ][ "data" ]
# -------------------------------------------------------------------------------------  
# Filter inner sign area 
#
# Returns: smallest contour
# -------------------------------------------------------------------------------------
def filter_sign():
    bot.update()
    sign_filtered = 0
    area_save = 0.0
    print 'Filtering sign area .................'
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)                                      # 0 - Set color range to search for blue shapes
    mask_image = cv2.inRange(hsv, lower_blue, upper_blue)                             # 1 - Mask only blue
    result_image = cv2.bitwise_and(image,image, mask= mask_image)                     # 2 - Convert masked color to white. Rest to black 
    result_image = cv2.bilateralFilter(result_image,9,75,75)                          # 3 - Optional: Blurring the result to de-noise
    result_image = cv2.cvtColor(result_image, cv2.COLOR_BGR2GRAY )                    # 4 - Convert to Gray (needed for binarizing)
    result_image = cv2.Canny(result_image,threshold1=90, threshold2=190)              # 5 - Find edges of all shapes
    contours, _ = cv2.findContours(result_image,
                                   cv2.RETR_LIST,
                                   cv2.CHAIN_APPROX_SIMPLE)                           # 6 - Find contours of all shapes
    contours = sorted(contours, key=cv2.contourArea, reverse=True) [:4]               # 7 - Select biggest 4; drop the rest
    contour_save = None
    objects_found = len(contours)
    if objects_found >= 1:               
        loop_count = 0
        loop_count = int(loop_count)
        rectangle_count = 0
        while loop_count < objects_found:
            cnt = contours[loop_count]
            M = cv2.moments(cnt)
            area = cv2.contourArea(cnt)
            epsilon = 0.1*cv2.arcLength(cnt,True)                                     
            approx = cv2.approxPolyDP(cnt,epsilon,True)
            if len (approx) == 4:
                if area > 5000:
                    if loop_count == 0:                                               # 8 - Keep the smallest aledged rectangle
                        rectangle_count += 1
                        contour_save = approx
                        area_save = area
                    elif area < area_save:
                        rectangle_count += 1
                        contour_save = approx
            loop_count += 1
        if rectangle_count > 0:
            sign_filtered = 1
    return sign_filtered, contour_save
# -------------------------------------------------------------------------------------
# Match images: crop, warp and intensivy the sign area and compare images
#
# Returns: next action
# -------------------------------------------------------------------------------------
def compare_images(contour_save):
    bot.update()
    print 'Comparing images .................... '
    signRight, signLeft, signTurn, signStop = get_reference_images()                   # read reference files
    contour_points = contour_save.reshape(4, 2)                                                      
    points_sorted = np.zeros((4, 2), dtype = "float32")                                # initializing output window in same order
    sum_of_points = contour_points.sum(axis = 1)                                       # determine top-left, top-right, bottom-right, bottom-left
    points_sorted[0] = contour_points[np.argmin(sum_of_points)]
    points_sorted[2] = contour_points[np.argmax(sum_of_points)]
    differance = np.diff(contour_points, axis = 1)
    points_sorted[1] = contour_points[np.argmin(differance)]
    points_sorted[3] = contour_points[np.argmax(differance)]
    (tl, tr, br, bl) = points_sorted
    widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[0] - bl[0]) ** 2))                  # need this; for example: it could as well be a parallelogram 
    widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[0] - tl[0]) ** 2))
    heightA = np.sqrt(((tr[1] - br[1]) ** 2) + ((tr[1] - br[1]) ** 2))
    heightB = np.sqrt(((tl[1] - bl[1]) ** 2) + ((tl[1] - bl[1]) ** 2))
    maxWidth = max(int(widthA), int(widthB))
    maxHeight = max(int(heightA), int(heightB))
    destination = np.array([[0, 0],[maxWidth - 2, 0],
                            [maxWidth - 2, maxHeight - 2],
                            [0, maxHeight - 2]],dtype = "float32")
    M = cv2.getPerspectiveTransform(points_sorted, destination)
    warped_image = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
    cv2.drawContours(image, [contour_save], -1, (255, 0, 0), 2)
    cv2.imshow("Cnt Found", image)
    cv2.waitKey(1)
    warped_image = cv2.cvtColor(warped_image, cv2.COLOR_BGR2GRAY)                      # convert to gray, blur and threshold
    warped_image = cv2.GaussianBlur(warped_image,(5,5),0)
    thrh,warped_image = cv2.threshold(warped_image,0,255,
                                      cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    (hc, wc) = signRight.shape[:2]                                                     # equalize shapes
    resized = cv2.resize(warped_image, (wc,hc),
                         interpolation=cv2.INTER_AREA)
    cv2.imshow ('resized', resized)
    cv2.waitKey(1)
    output=signRight                                                                   # create window for bitwise output
    print 'Mean Squared Error comparing ........'
    mse_v = mse(resized,signRight)
    if mse_v > 5000:
        mse_v = mse(resized,signLeft)
        if mse_v > 5000:
            mse_v = mse(resized,signTurn)
            if mse_v > 5000:
                mse_v = mse(resized,signStop)
                if mse_v > 5000:
                    next_action = 'NO MATCH'
                else:
                    next_action = 'STOP'
            else:
                next_action = 'TURN'
        else:
            next_action = 'LEFT'
    else:
        next_action = 'RIGHT'
    return next_action
# -------------------------------------------------------------------------------------
# Read the reference files from disk Blurring and thresholding to assure the pictures
# corrolate in values with the printed sign  
#
# Returns: images read 
# -------------------------------------------------------------------------------------    
def get_reference_images():
    print 'Reading reference images ............'
    signRight = cv2.imread('signright.jpg',0)
    if signRight != None:
        signRight = cv2.GaussianBlur(signRight,(5,5),0)
        _,signRight = cv2.threshold(signRight,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
        signLeft = cv2.imread('signleft.jpg',0)
        if signLeft != None:
            signLeft = cv2.GaussianBlur(signLeft,(5,5),0)
            _,signLeft = cv2.threshold(signLeft,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
            signTurn = cv2.imread('signturn.jpg',0)
            if signTurn != None:
                signTurn = cv2.GaussianBlur(signTurn,(5,5),0)
                _,signTurn = cv2.threshold(signTurn,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
                signStop = cv2.imread('signstop.jpg',0)
                if signStop != None:
                    signStop = cv2.GaussianBlur(signStop,(5,5),0)
                    _,signStop = cv2.threshold(signStop,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    else:
        print 'Error(s) reading files !!!'
        wait = raw_input()
    return signRight, signLeft, signTurn, signStop
# -------------------------------------------------------------------------------------
# Compare 2 images Both routines can be used (current use: MSE)
#
# Input: image from disk, image found on sign
# Returns: number of non-zero pixels
# -------------------------------------------------------------------------------------
def bwc(imageA, imageB):
    cv2.bitwise_xor(imageA,imageB,output,mask=None)
    diff=cv2.countNonZero(output)
    #cv2.imshow('output',output)                                                       # (un)comment to hide/watch output images one by one
    #cv2.waitKey(0)
    return diff
def mse(imageA, imageB):                                                               # Mean Squared Error = differance in pixel intensity 
    err = np.sum((imageA.astype("float") - imageB.astype("float")) ** 2)
    err /= float(imageA.shape[0] * imageA.shape[1])
    return err
#--------------------------------------------------------------------------------------- Set up a parser for command line arguments
parser = argparse.ArgumentParser( "Gets images from the robot" )
parser.add_argument( "hostname", default="localhost", nargs='?',
                     help="The ip address of the robot" )
args = parser.parse_args()
# -------------------------------------------------------------------------------------- Connect to the robot
#bot = py_websockets_bot.WebsocketsBot( args.hostname )
bot = py_websockets_bot.WebsocketsBot( "192.168.42.1" )
#--------------------------------------------------------------------------------------- Initialize mini driver pins       
sensorConfiguration = py_websockets_bot.mini_driver.SensorConfiguration(
    configD12=py_websockets_bot.mini_driver.PIN_FUNC_ULTRASONIC_READ,                  # SeeeD 3-pin Ultrasonic sensor
    configD13=py_websockets_bot.mini_driver.PIN_FUNC_INACTIVE, 
    configA0=py_websockets_bot.mini_driver.PIN_FUNC_ANALOG_READ, 
    configA1=py_websockets_bot.mini_driver.PIN_FUNC_DIGITAL_READ,                      # Sharp IR switch RIGHT
    configA2=py_websockets_bot.mini_driver.PIN_FUNC_DIGITAL_READ,                      # Sharp IR switch LEFT
    configA3=py_websockets_bot.mini_driver.PIN_FUNC_DIGITAL_READ,                      # Grove Line sensor RIGHT
    configA4=py_websockets_bot.mini_driver.PIN_FUNC_DIGITAL_READ,                      # Grove Line sensor MIDDLE
    configA5=py_websockets_bot.mini_driver.PIN_FUNC_DIGITAL_READ,                      # Grove Line sensor LEFT
    leftEncoderType=py_websockets_bot.mini_driver.ENCODER_TYPE_SINGLE_OUTPUT,          # Single encoder
    rightEncoderType=py_websockets_bot.mini_driver.ENCODER_TYPE_SINGLE_OUTPUT )        # Single encoder
robot_config = bot.get_robot_config()
robot_config.miniDriverSensorConfiguration = sensorConfiguration
bot.set_robot_config( robot_config )
bot.update()                                                                           # Update any background communications with the robot
time_out (100)                                                                         # Sleep to avoid overload of the web server on the robot
#--------------------------------------------------------------------------------------
if __name__ == "__main__":
    #---------------------------------------------------------------------------------- Start streaming images from the camera
    bot.start_streaming_camera_images()
    time_out (200)
    #----------------------------------------------------------------------------------    
    while next_action != 'STOP':
        marker_found == 0
        bot.update()
        tilt_angle = 90
        pan_angle = 90
        bot.set_neck_angles( pan_angle,tilt_angle)
        time_out (20)
        find_marker()       
        # -----------------------------------------------------------------------------
        # FIND MARKER (until blue object found)
        # -----------------------------------------------------------------------------
        shuffle = 0
        while marker_found == 0:
            if shuffle > 1:
                motor_speed = 70.0
                bot.set_motor_speeds( -motor_speed, motor_speed )
                time_out (34)
                bot.set_motor_speeds (0.0 , 0.0)
                motor_speed = 40.0
                shuffle = 0
            bot.update()
            if pan_angle < max_pan_angle:
               pan_angle += 2.5
            else:
                pan_angle = min_pan_angle
                marker_found = 0
                shuffle += 1 
            bot.set_neck_angles( pan_angle,tilt_angle)
            time_out (38)
            find_marker()
        print'pan angle                            =', pan_angle
        # -----------------------------------------------------------------------------
        # MOVE_TO_MARKER (until <= 40 cm)
        # -----------------------------------------------------------------------------
        list_width = []
        list_speed = []
        pan_angle = 90
        speed_adjust = 0.0
        w_save = w - 1
        bot.set_neck_angles( pan_angle,tilt_angle)
        read_sensors()
        while w < max_width:
            if sensor_data != 24:                                                     # Test for any IR sensor signal
               bot.set_motor_speeds( 0.0, 0.0 )
               print 'Obstacle detected!', sensor_data
               break
            list_width.append (w)
            if w > w_save:
                speed_adjust = 1.1 *(((centroid_x - 320) / 640.000) * 50)
                speed_adjust = round (speed_adjust, 1)
                motor_l = motor_speed + speed_adjust
                motor_r = motor_speed - speed_adjust
                list_speed.append (w)
                w_save = w
                bot.set_motor_speeds( motor_l, motor_r )
            bot.update()
            time_out (10)                                                             # Need delays to avoid overload of webserver !
            read_sensors()
            time_out(10)
            find_marker()
            time_out (16)                                                             # Need delays to avoid overload of camera buffer !
        bot.set_motor_speeds (0.0, 0.0)
        time_out (1)
        print'found  =',list_width, len(list_width), 'times'
        print'speeds =',list_speed, len(list_speed), 'times'
        print'width / range / speed = %d / %d / %d ' % (w, camera_range, speed_adjust)
        # -----------------------------------------------------------------------------
        # READ SIGN (until match) and ACT_ON_SIGN (next action or stop)
        # -----------------------------------------------------------------------------
        sign_filtered, contour_save = filter_sign()
        if sign_filtered == 1:
            next_action = compare_images(contour_save)
        else:
            time_out (200)
        bot.update()
        motor_speed = 70.0
        bot.set_motor_speeds( 0.0, 0.0 )
        if next_action == 'STOP':
            print 'STOP'
            wait = raw_input()
            pass
        if next_action == 'RIGHT':
            print 'RIGHT'
            bot.set_motor_speeds( motor_speed, -motor_speed )
            time_out (65)
            bot.set_motor_speeds( 0.0, 0.0 )
            next_action = 'START'
             bot.update ()
            image = None                                                              # Routine to avoid using images in camera buffer
            while image == None:
                image, _  = bot.get_latest_camera_image(1.0)                          # Force latest image (= new sign)
                time_out (30)
        if next_action == 'LEFT':
            print 'LEFT'
            bot.set_motor_speeds( -motor_speed, motor_speed )
            time_out (100)
            bot.set_motor_speeds( 0.0, 0.0 )
            next_action = 'START'
            bot.update ()
            image = None                                                              # Routine to avoid using images in camera buffer
            while image == None:
                image, _  = bot.get_latest_camera_image(1.0)                          # Force latest image (= new sign)
                time_out (30)
        if next_action == 'TURN':
            print 'TURN'
            bot.set_motor_speeds( motor_speed, -motor_speed )
            time_out (170)
            bot.set_motor_speeds( 0.0, 0.0 )
            next_action = 'START'
            bot.update ()
            image = None                                                              # Routine to avoid using images in camera buffer
            while image == None:
                image, _  = bot.get_latest_camera_image(1.0)                          # Force latest image (= new sign)
                time_out (30)
        if next_action == 'NO MATCH':
            print 'NO MATCH'
        motor_speed = 40.0
        #cv2.destroyAllWindows()
    # --------------------------------------------------------------------------------- Finalize    
    cv2.destroyAllWindows()
    bot.stop_streaming_camera_images()
    bot.set_motor_speeds( 0.0, 0.0 )
    bot.centre_neck()
    print 'FINISHED'
    bot.disconnect()
