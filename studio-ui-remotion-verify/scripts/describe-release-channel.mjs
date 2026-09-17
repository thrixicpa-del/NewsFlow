import { releaseChannel } from "./release-channel.mjs";

const args = process.argv.slice(2);
const channel = args.includes("--channel") ? args[args.indexOf("--channel") + 1] : "";
process.stdout.write(`${JSON.stringify(releaseChannel(channel))}\n`);
