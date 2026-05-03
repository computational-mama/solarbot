import ChatFlow from "./core/ChatFlow";
import dotenv from "dotenv";
import { startBatteryStatus } from "./status/battery-status";
import { startWifiStatus } from "./status/wifi-status";
import { startVpnStatus } from "./status/vpn-status";
import { startAdminServer } from "./admin/admin-server";

dotenv.config();

const adminPort = parseInt(process.env.WHISPLAY_ADMIN_PORT || "0", 10);
if (adminPort) startAdminServer(adminPort);

startBatteryStatus();
startWifiStatus();
startVpnStatus();

new ChatFlow({
  enableCamera: process.env.ENABLE_CAMERA === "true",
});
