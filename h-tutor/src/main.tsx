import React from "react";
import ReactDOM from "react-dom/client";
import App from "./panel/App";
import "./panel/styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
