FROM cyberbotics/webots:R2023b-ubuntu22.04

WORKDIR /app

COPY . .

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    xvfb \
    libxcb-cursor0 \
    libxcb-keysyms1 \
    libxcb-xinerama0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-render-util0 \
    libxcb-util1 \
    libxkbcommon-x11-0 \
    libxrender1 \
    iverilog \
    octave

RUN pip3 install -r docker_requirements.txt

ENV WEBOTS_HEADLESS=1

CMD ["python3"]
