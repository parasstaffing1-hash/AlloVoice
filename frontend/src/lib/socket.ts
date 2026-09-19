"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { io, Socket } from "socket.io-client";

const SOCKET_URL = process.env.NEXT_PUBLIC_SOCKET_URL || "http://localhost:8000";

let socket: Socket | null = null;

export function getSocket(): Socket {
  if (!socket) {
    socket = io(SOCKET_URL, {
      autoConnect: false,
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
    });
  }
  return socket;
}

export function useSocket() {
  const socketRef = useRef<Socket | null>(null);

  useEffect(() => {
    socketRef.current = getSocket();
    if (!socketRef.current.connected) {
      socketRef.current.connect();
    }
    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, []);

  return socketRef.current;
}

export function useSocketEvent(event: string, callback: (...args: any[]) => void) {
  const socket = useSocket();

  useEffect(() => {
    if (!socket) return;
    socket.on(event, callback);
    return () => {
      socket.off(event, callback);
    };
  }, [socket, event, callback]);
}

export function useDispatch(businessId: string) {
  const socket = useSocket();
  const [jobs, setJobs] = useState<any[]>([]);
  const [technicians, setTechnicians] = useState<any[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!socket || !businessId) return;

    socket.on("connect", () => {
      setConnected(true);
      socket.emit("join_dispatch", { business_id: businessId });
    });

    socket.on("disconnect", () => setConnected(false));

    socket.on("new_job", (job: any) => {
      setJobs((prev) => [job, ...prev]);
    });

    socket.on("job_updated", (job: any) => {
      setJobs((prev) => prev.map((j) => (j.id === job.id ? job : j)));
    });

    return () => {
      socket.off("new_job");
      socket.off("job_updated");
    };
  }, [socket, businessId]);

  return { jobs, technicians, connected };
}
