
import cv2
import numpy as np
import serial

from time import sleep
import time

from numpy.ma.core import angle

# from picamera2 import Picamera2
# import serial
import utlis

# Camera settings
CAM_WIDTH = 640
CAM_HEIGHT = 480

# Regions of Interest
ROI1 = [20, 170, 240, 220]  # Left lane
ROI2 = [400, 170, 620, 220]  # Right lane
ROI3 = [200, 300, 440, 350]  # Color markers
ROI4 = [0, 160, 640, 480]  # Signal detection area

# Color ranges
LOWER_BLACK = np.array([0, 0, 0])
UPPER_BLACK = np.array([180, 255, 50])

LOWER_ORANGE = np.array([5, 50, 50])
# LOWER_ORANGE = np.array([10, 100, 100])
UPPER_ORANGE = np.array([25, 255, 255])
LOWER_BLUE = np.array([90, 50, 50])
# LOWER_BLUE = np.array([90, 100, 100])
UPPER_BLUE = np.array([130, 255, 255])

# Control parameters
kp = 0.02
kd = 0.006
straightConst = 95
turnThresh = 150
exitThresh = 1500
tDeviation = 25
sharpRight = straightConst - tDeviation
sharpLeft = straightConst + tDeviation
maxRight = straightConst - 50
maxLeft = straightConst + 50

# Signal detection constants
PX_TO_CM = 0.00264583333
FOCAL_DISTANCE = 3  # cm
SIGNAL_SIZE = 10  # cm
WEIGHT = 5
OBJECT_SIZE = 30  # pixels
FRAME_WIDTH = 640  # Should match CAM_WIDTH
FRAME_HEIGHT = 480  # Should match CAM_HEIGHT


def find_contours(frame, lower_color, upper_color, roi):
    x1, y1, x2, y2 = roi
    roi_frame = frame[y1:y2, x1:x2]

    hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower_color, upper_color)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return contours


def max_contour(contours):
    if not contours:
        return (0, None)
    largest = max(contours, key=cv2.contourArea)
    return (cv2.contourArea(largest), largest)


def display_roi(frame, rois, color):
    for roi in rois:
        x1, y1, x2, y2 = roi
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    return frame


# def process_signal_data(data):
#     # if len(data) < 5:
#     #     return "INVALID DATA"
#
#     if data[0] == 1:
#         return "left" if data[4] < 15 else "centered"
#     elif data[0] == 0:
#         return "right" if data[4] < 15 else "centered"
#     return "WALL FOLLOW"

def process_signal_data(data):
    # if len(data) < 5:
    #     return "INVALID DATA"

    if data[0] == 1:
        if data[4] < -5:
            # ser.write(b"left\n")
            # return "left"
            return "centered"
        else:
            # ser.write(b"centered\n")
            # print(data[4])
            # return "centered"
            return "left"

    elif data[0] == 0:
        if data[4] < 15:
            # ser.write(b"right\n")
            return "right"
        else:
            # ser.write(b"centered\n")
            return "centered"

    # ser.write(b"FOLLOW\n")
    return "WALL FOLLOW"
    # return {angle}
arduino = serial.Serial(port='/dev/ttyUSB0', baudrate=115200, timeout=0.05)  # For Linux

time.sleep(2)  # Wait for Arduino to reset

# ser = serial.Serial('/dev/ttyACMC0', 115200, timeout=1.0)
#     ser.flush()
def main():
    # time.sleep(3)
    #
    # # initialize camera
    # picam2 = Picamera2()
    # picam2.preview_configuration.main.size = (640, 480)
    # picam2.preview_configuration.main.format = "RGB888"
    # picam2.preview_configuration.controls.FrameRate = 30
    # picam2.preview_configuration.align()
    # picam2.configure("preview")
    # picam2.start()

    # Initialize webcam
    # cap = picam2.capture_array()
    cap = cv2.VideoCapture(0)
    # cap = cv2.VideoCapture('wro2020-fe-POV2-120d-ezgif.com-resize.gif')
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)

    # State variables
    lTurn = rTurn = False
    t = angle = prevAngle = aDiff = prevDiff = 0
    lDetected = start = False
    debug = True
    turnDir = "none"

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)

        # Extract ROI4 region for signal detection
        x1, y1, x2, y2 = ROI4
        roi4_frame = frame[y1:y2, x1:x2].copy()

        # Signal detection
        signal_img, signal_data = utlis.signal_detection(
            roi4_frame, SIGNAL_SIZE, WEIGHT, OBJECT_SIZE,
            FOCAL_DISTANCE, PX_TO_CM, FRAME_WIDTH
        )

        # Find contours for lanes and markers
        cListLeft = find_contours(frame, LOWER_BLACK, UPPER_BLACK, ROI1)
        cListRight = find_contours(frame, LOWER_BLACK, UPPER_BLACK, ROI2)
        cListOrange = find_contours(frame, LOWER_ORANGE, UPPER_ORANGE, ROI3)
        cListBlue = find_contours(frame, LOWER_BLUE, UPPER_BLUE, ROI3)

        # Get areas
        leftArea, _ = max_contour(cListLeft)
        rightArea, _ = max_contour(cListRight)
        orangeArea, _ = max_contour(cListOrange)
        blueArea, _ = max_contour(cListBlue)

        # Process signal data
        action = process_signal_data(signal_data)
        # print(f"Action: {action}")

        # Marker detection
        if orangeArea > 100:
            lDetected = True
            if turnDir == "none":
                turnDir = "right"
        elif blueArea > 100:
            lDetected = True
            if turnDir == "none":
                turnDir = "left"

        # Steering calculation
        aDiff = rightArea - leftArea
        angle = int(max(straightConst + aDiff * kp + (aDiff - prevDiff) * kd, 0))

        # Turn detection
        if leftArea <= turnThresh and not rTurn:
            lTurn = True
        elif rightArea <= turnThresh and not lTurn:
            rTurn = True

        # Turn exit logic
        if (rTurn and rightArea > exitThresh) or (lTurn and leftArea > exitThresh):
            lTurn = rTurn = False
            prevDiff = 0
            if lDetected:
                t += 1
                lDetected = False
                print(f"Completed turns: {t}")

        # Angle clamping
        angle = np.clip(angle, maxRight, maxLeft)# if rTurn or lTurn else \
            # np.clip(angle, sharpRight, sharpLeft)

        # Debug display
        if debug:
            debug_frame = frame.copy()
            debug_frame = display_roi(debug_frame, [ROI1, ROI2, ROI3, ROI4], (255, 0, 255))

            # Draw contours
            for roi, contours in [(ROI1, cListLeft), (ROI2, cListRight), (ROI3, cListOrange)]:
                x, y, w, h = roi
                cv2.drawContours(debug_frame[y:h, x:w], contours, -1, (0, 255, 0), 2)

            # Display info
            status = f"Angle: {angle} | Turns: {t} | L: {leftArea} | R: {rightArea}"
            cv2.putText(debug_frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imshow("Debug View", debug_frame)
            cv2.imshow("Signal Detection", signal_img)

        prevDiff = aDiff
        prevAngle = angle

        # Process signal data
        action = process_signal_data(signal_data)
        print(f"Action: {action}")

        if action == "left":
            angle = 42  # Constant angle for left
            arduino.write(f"{angle}\n".encode())
        elif action == "right":
            angle = 142  # Constant angle for right
            arduino.write(f"{angle}\n".encode())
        elif action == "centered":
            angle = 92
            arduino.write(f"{angle}\n".encode())
        else:
            # Use the calculated angle from PD control
            arduino.write(f"{angle}\n".encode())

        # Exit conditions
        if t >= 12 and abs(angle - straightConst) <= 10:
            print("Lap completed!")
            # ser.write(b"stop\n")
            break
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()

# import cv2
# import numpy as np
# import serial
# import time
# from picamera2 import Picamera2
# import utlis
#
# # Camera settings
# CAM_WIDTH = 640
# CAM_HEIGHT = 480
#
# # Regions of Interest
# ROI1 = [20, 170, 240, 220]
# ROI2 = [400, 170, 620, 220]
# ROI3 = [200, 300, 440, 350]
# ROI4 = [60, 180, 580, 380]
#
# # Color ranges
# LOWER_BLACK = np.array([0, 0, 0])
# UPPER_BLACK = np.array([180, 255, 50])
# LOWER_ORANGE = np.array([5, 50, 50])
# UPPER_ORANGE = np.array([25, 255, 255])
# LOWER_BLUE = np.array([90, 50, 50])
# UPPER_BLUE = np.array([130, 255, 255])
#
# # Control parameters
# kp = 0.02
# kd = 0.006
# straightConst = 92
# turnThresh = 150
# exitThresh = 1500
# tDeviation = 25
# sharpRight = straightConst + tDeviation
# sharpLeft = straightConst - tDeviation
# maxRight = straightConst + 50
# maxLeft = straightConst - 50
#
# # Signal detection
# PX_TO_CM = 0.00264583333
# FOCAL_DISTANCE = 3  # cm
# SIGNAL_SIZE = 10  # cm
# WEIGHT = 5
# OBJECT_SIZE = 30
# FRAME_WIDTH = CAM_WIDTH
# FRAME_HEIGHT = CAM_HEIGHT
#
#
# def find_contours(frame, lower_color, upper_color, roi):
#     x1, y1, x2, y2 = roi
#     roi_frame = frame[y1:y2, x1:x2]
#     hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
#     mask = cv2.inRange(hsv, lower_color, upper_color)
#
#     kernel = np.ones((5, 5), np.uint8)
#     mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
#     mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
#     contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
#     return contours
#
#
# def max_contour(contours):
#     if not contours:
#         return (0, None)
#     largest = max(contours, key=cv2.contourArea)
#     return (cv2.contourArea(largest), largest)
#
#
# def display_roi(frame, rois, color):
#     for roi in rois:
#         x1, y1, x2, y2 = roi
#         cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
#     return frame
#
#
# def process_signal_data(data):
#     if data[0] == 1:
#         return "centered" if data[4] < -5 else "left"
#     elif data[0] == 0:
#         return "right" if data[4] < 15 else "centered"
#     return "WALL FOLLOW"
#
#
# # Serial setup
# arduino = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.05)
# time.sleep(2)
#
#
# def main():
#     # Initialize PiCamera
#     picam2 = Picamera2()
#     picam2.preview_configuration.main.size = (CAM_WIDTH, CAM_HEIGHT)
#     picam2.preview_configuration.main.format = "RGB888"
#     picam2.configure("preview")
#     picam2.start()
#     time.sleep(2)
#
#     # State variables
#     lTurn = rTurn = False
#     t = angle = prevAngle = aDiff = prevDiff = 0
#     lDetected = start = False
#     debug = True
#     turnDir = "none"
#
#     while True:
#         frame = picam2.capture_array()
#         # frame = cv2.flip(frame, 1)
#
#         x1, y1, x2, y2 = ROI4
#         roi4_frame = frame[y1:y2, x1:x2].copy()
#
#         signal_img, signal_data = utlis.signal_detection(
#             roi4_frame, SIGNAL_SIZE, WEIGHT, OBJECT_SIZE,
#             FOCAL_DISTANCE, PX_TO_CM, FRAME_WIDTH
#         )
#
#         # Contour detection
#         cListLeft = find_contours(frame, LOWER_BLACK, UPPER_BLACK, ROI1)
#         cListRight = find_contours(frame, LOWER_BLACK, UPPER_BLACK, ROI2)
#         cListOrange = find_contours(frame, LOWER_ORANGE, UPPER_ORANGE, ROI3)
#         cListBlue = find_contours(frame, LOWER_BLUE, UPPER_BLUE, ROI3)
#
#         # Area calculations
#         leftArea, _ = max_contour(cListLeft)
#         rightArea, _ = max_contour(cListRight)
#         orangeArea, _ = max_contour(cListOrange)
#         blueArea, _ = max_contour(cListBlue)
#
#         # Marker-based logic
#         action = process_signal_data(signal_data)
#         if orangeArea > 100:
#             lDetected = True
#             if turnDir == "none": turnDir = "right"
#         elif blueArea > 100:
#             lDetected = True
#             if turnDir == "none": turnDir = "left"
#
#         # Process signal data
#         print(f"Action: {action}")
#
#         # PD control
#         aDiff = rightArea - leftArea
#         angle = int(max(straightConst + aDiff * kp + (aDiff - prevDiff) * kd, 0))
#
#         if leftArea <= turnThresh and not rTurn:
#             lTurn = True
#         elif rightArea <= turnThresh and not lTurn:
#             rTurn = True
#
#         if (rTurn and rightArea > exitThresh) or (lTurn and leftArea > exitThresh):
#             lTurn = rTurn = False
#             prevDiff = 0
#             if lDetected:
#                 t += 1
#                 lDetected = False
#                 print(f"Completed turns: {t}")
#
#         # Clamp angle
#         angle = np.clip(angle, maxRight, maxLeft) if rTurn or lTurn else \
#             np.clip(angle, sharpRight, sharpLeft)
#
#         # Debug visualization
#         if debug:
#             debug_frame = frame.copy()
#             debug_frame = display_roi(debug_frame, [ROI1, ROI2, ROI3, ROI4], (255, 0, 255))
#             for roi, contours in [(ROI1, cListLeft), (ROI2, cListRight), (ROI3, cListOrange)]:
#                 x, y, w, h = roi
#                 cv2.drawContours(debug_frame[y:h, x:w], contours, -1, (0, 255, 0), 2)
#             status = f"Angle: {angle} | Turns: {t} | L: {leftArea} | R: {rightArea}"
#             cv2.putText(debug_frame, status, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
#             cv2.imshow("Debug View", debug_frame)
#             cv2.imshow("Signal Detection", signal_img)
#
#         prevDiff = aDiff
#         prevAngle = angle
#
#         # Write to Arduino
#         if action == "left":
#             arduino.write(f"45\n".encode())
#         elif action == "right":
#             arduino.write(f"145\n".encode())
#         elif action == "centered":
#             arduino.write(f"95\n".encode())
#         else:
#             arduino.write(f"{angle}\n".encode())
#
#         if t >= 12 and abs(angle - straightConst) <= 10:
#             print("Lap completed!")
#             break
#         if cv2.waitKey(1) & 0xFF == ord('q'):
#             break
#
#     cv2.destroyAllWindows()
#
#
# if __name__ == '__main__':
#     main()