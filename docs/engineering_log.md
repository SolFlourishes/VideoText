Engineering Notebook
Milestone 1
Goal: Open a local MP4 file and read its basic properties.
Result: ✅ Success. The application correctly opened the sample video and reported its frame rate (23.98 FPS), total frames (5,155), and duration (215.01 seconds).
What we learned: The development environment is working correctly, OpenCV is installed and functioning, and the application can access video files from the project directory.
Next milestone: Save the first frame of the video as a PNG image.

Milestone 2: Extract the First Frame
Goal
Open a video and save the first frame as an image.
Result
✅ Success
The program:
•	Opened the video. 
•	Read the first frame. 
•	Saved it as: 
output/frame_0001.png
What We Learned
•	OpenCV can read frames from our videos. 
•	Our output folder is working correctly. 
•	We now have the basic building block needed before OCR.

Milestone 3 - Part 1
Goal
Create a reusable function that opens a video.
Result
✅ Success
What We Learned
•	We can reuse functions across Python files. 
•	video_reader.py is becoming a library instead of just a script. 
•	frame_extractor.py now depends on video_reader.py instead of duplicating code. 


## Milestone 3

Completed

- Refactored video opening into a reusable function.
- Created frame_extractor.py.
- Successfully processed every frame in the sample video.
- Verified 5,155 frames were read.

Next

Calculate visual difference between consecutive frames.
