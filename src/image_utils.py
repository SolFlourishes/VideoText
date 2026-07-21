import cv2


def calculate_frame_difference(frame1, frame2):
    """
    Calculate the average visual difference between two frames.
    Optimized for speed by comparing grayscale thumbnails.
    """

    # Convert to grayscale
    gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)

    # Resize to a smaller image
    gray1 = cv2.resize(gray1, (320, 180))
    gray2 = cv2.resize(gray2, (320, 180))

    difference = cv2.absdiff(gray1, gray2)

    return difference.mean()