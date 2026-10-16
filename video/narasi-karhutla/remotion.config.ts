import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
// The narration is the point of the film, so the audio gets real bitrate.
Config.setAudioCodec("aac");
Config.setCodec("h264");
Config.setCrf(18);
