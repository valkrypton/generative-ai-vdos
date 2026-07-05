import { Config } from "@remotion/cli/config";

// 1920x1080 h264 to match the FFmpeg assembler's per-scene clips.
Config.setVideoImageFormat("jpeg");
Config.setCodec("h264");
Config.setPixelFormat("yuv420p");
Config.setOverwriteOutput(true);
