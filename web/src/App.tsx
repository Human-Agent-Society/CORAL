import { useState } from "react";
import Header from "./components/Header";
import Overview from "./pages/Overview";
import Dag from "./pages/Dag";
import Knowledge from "./pages/Knowledge";
import Logs from "./pages/Logs";

type Tab = "overview" | "dag" | "knowledge" | "logs";

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("overview");

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <Header activeTab={activeTab} onTabChange={setActiveTab} />

      <div className="flex-1 min-h-0 grid grid-cols-2">
        {activeTab === "overview" && <Overview />}
        {activeTab === "dag" && <Dag />}
        {activeTab === "knowledge" && <Knowledge />}
        {activeTab === "logs" && <Logs />}
      </div>
    </div>
  );
}
