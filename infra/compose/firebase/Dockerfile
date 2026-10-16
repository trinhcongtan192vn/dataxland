# Firebase Auth Emulator cho local (spec 00 §4, §7).
FROM node:22.11-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless && rm -rf /var/lib/apt/lists/*
RUN npm install -g firebase-tools@13.29.1
WORKDIR /srv
COPY firebase.json .firebaserc ./
EXPOSE 9099 4400
CMD ["firebase", "emulators:start", "--only", "auth", "--project", "dataxland-local"]
