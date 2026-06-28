# AI Tracking Options

These are practical GitHub-based options to add AI tracking to this project. "Tracking" can mean different things: detecting a face/object in each frame, steering servos to keep it centered, recognizing a known person/object, or running heavier analysis on an Android/PC client.

## Option 1: ESP-WHO On-Device Face Detection

GitHub: https://github.com/espressif/esp-who

ESP-WHO is Espressif's own computer vision framework for ESP chips. It is the most natural route for on-device face detection and face recognition on ESP32-S3-class hardware.

Pros:

- Runs on the ESP32-S3 without requiring a phone or PC.
- Mature Espressif project with face detection/recognition examples.
- Gives bounding boxes that can be converted into pan/tilt steering commands.
- Good fit if the first goal is "track a face in frame."

Cons:

- More naturally ESP-IDF than Arduino/PlatformIO Arduino, so integration into this current firmware is a larger refactor.
- Face detection uses lower-resolution RGB frames, so it competes with high-resolution JPEG streaming.
- Tracking plus Wi-Fi streaming plus SD recording will need mode switching or careful task scheduling.

Best use here:

- Add a "Face Track" mode that lowers camera resolution, detects face boxes, exposes `/tracking/status`, and optionally drives two GPIO/servo outputs.

## Option 2: Edge Impulse Custom Object Detection

GitHub examples:

- https://github.com/Tiny-Prism-Labs/ESP32-S3_Object_Identification_EI
- https://github.com/mpous/xiao-esp32s3-camera-edgeimpulse

Edge Impulse is the best route if you want to train the camera to recognize your own objects, poses, parts, tools, pets, or targets.

Pros:

- Good workflow for custom models.
- Existing XIAO ESP32-S3 Sense examples.
- Can classify/detect project-specific objects instead of only faces.
- Easier training pipeline than building an ESP-DL model manually.

Cons:

- Object detection models are heavier than image classification.
- Practical frame rate is much lower than raw streaming.
- Most examples are demos, not drop-in webserver integrations.
- Free/hosted tooling workflow may not fit every offline use case.

Best use here:

- Add an "AI classify/detect snapshot" button first, then later run periodic detection and draw/store results.

## Option 3: Browser/Android TensorFlow.js Tracking

GitHub: https://github.com/cifertech/ObjectDetection_ESP32cam

This approach streams camera frames to a browser or Android WebView and runs TensorFlow.js detection on the client instead of on the ESP32.

Pros:

- Keeps ESP32 firmware simpler.
- Lets the phone/browser do heavier AI work.
- Can use larger pretrained models than the ESP32 can handle.
- Does not reduce the ESP32 camera firmware to tiny inference frames.

Cons:

- Requires the client app/browser to stay connected and do the tracking.
- Latency depends on Wi-Fi and phone/browser performance.
- Servo tracking commands need a return API from client to ESP32.
- Not fully standalone.

Best use here:

- Add JavaScript detection in the web UI or Android app, then POST target center coordinates back to `/tracking/target`.

## Option 4: WebMCU Vision Local Training Workflow

GitHub: https://github.com/webmcu-ai/webmcu-vision-web

This is a newer browser-based TinyML workflow targeting XIAO ESP32-S3 Sense style hardware. It focuses on local image collection, training, weight export, and deployment.

Pros:

- Designed around XIAO ESP32-S3 Sense workflows.
- Local browser workflow is convenient for data collection and training.
- Useful if you want a repeatable "collect images, train, deploy" loop.
- Aligns well with the SD file browser/storage features just added.

Cons:

- Newer project, so expect more integration work and less battle-tested behavior.
- It is more of a training/deployment workflow than a finished tracking module.
- You still need firmware glue to turn inference output into tracking control.

Best use here:

- Use SD photo capture as the data collection source, train locally, then integrate exported weights later.

## Option 5: Simple Color/Motion Tracking

GitHub reference for camera/servo tracking style:

- https://github.com/AshishA26/Turret-Face-Tracker
- https://robotzero.one/face-tracking-esp32-cam/

This is not always "AI", but it is often the fastest useful tracker. Convert frames to low resolution, threshold for color or motion, find the centroid, and steer.

Pros:

- Fastest and simplest to implement.
- Can run alongside webserver features more easily than ML inference.
- Good for tracking a colored marker, LED, ball, toolhead, or high-contrast moving target.
- Easy to expose tuning controls in the current web UI.

Cons:

- Not semantic; it does not know "person", "face", or "object type."
- Sensitive to lighting and background.
- Needs target-specific thresholds.

Best use here:

- Add `/tracking/color` settings, process occasional low-res frames, and output target center coordinates before attempting ML.

## Recommendation

Start with Option 5 for mechanical tracking controls and UI plumbing, then add either Option 1 for face tracking or Option 2 for custom object detection. If your phone is always part of the workflow, Option 3 gives the best detection capability without overloading the ESP32-S3.
