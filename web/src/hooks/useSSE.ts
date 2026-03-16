import { useEffect, useRef } from "react";

type SSEHandler = (data: unknown) => void;

export function useSSE(handlers: Record<string, SSEHandler>) {
  const handlersRef = useRef(handlers);
  useEffect(() => {
    handlersRef.current = handlers;
  });

  useEffect(() => {
    const source = new EventSource("/api/events");

    source.addEventListener("connected", () => {});

    const eventTypes = [
      "attempt:new",
      "attempt:update",
      "note:update",
      "log:update",
      "eval:update",
    ];

    for (const type of eventTypes) {
      source.addEventListener(type, (e) => {
        try {
          const data = JSON.parse((e as MessageEvent).data);
          const handler = handlersRef.current[type];
          if (handler) handler(data);
        } catch {
          // ignore parse errors
        }
      });
    }

    // Cross-tab sync: reload when another tab switches runs
    source.addEventListener("run:switched", () => {
      window.location.reload();
    });

    source.onerror = () => {};

    return () => source.close();
  }, []);
}
