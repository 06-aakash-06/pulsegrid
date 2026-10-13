import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./app/App";
import "@fontsource-variable/inter";
import "./styles/global.css";
import "./styles/hospital.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
