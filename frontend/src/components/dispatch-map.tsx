"use client";

import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

interface MapMarker {
  id: string;
  latitude: number;
  longitude: number;
  label: string;
  status: string;
  type: "job" | "technician";
}

interface DispatchMapProps {
  markers?: MapMarker[];
  center?: [number, number];
  zoom?: number;
  height?: string;
  onMarkerClick?: (id: string) => void;
}

const STATUS_COLORS: Record<string, string> = {
  scheduled: "#a855f7",
  in_progress: "#f97316",
  completed: "#22c55e",
  quote_requested: "#eab308",
  quote_sent: "#3b82f6",
  quote_approved: "#22c55e",
};

export default function DispatchMap({
  markers = [],
  center = [-0.1276, 51.5074], // London
  zoom = 11,
  height = "500px",
  onMarkerClick,
}: DispatchMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);

  useEffect(() => {
    if (!mapContainer.current) return;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors",
          },
        },
        layers: [
          {
            id: "osm",
            type: "raster",
            source: "osm",
          },
        ],
      },
      center,
      zoom,
    });

    map.current.addControl(new maplibregl.NavigationControl(), "top-right");
    map.current.addControl(new maplibregl.ScaleControl(), "bottom-left");

    return () => {
      map.current?.remove();
    };
  }, []);

  useEffect(() => {
    if (!map.current) return;

    // Clear existing markers
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];

    markers.forEach((marker) => {
      const el = document.createElement("div");
      el.className = "dispatch-marker";
      el.style.cssText = `
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background: ${STATUS_COLORS[marker.status] || "#6b7280"};
        border: 3px solid white;
        box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
        color: white;
        font-weight: bold;
      `;
      el.textContent = marker.type === "technician" ? "T" : "J";
      el.title = marker.label;

      if (onMarkerClick) {
        el.addEventListener("click", () => onMarkerClick(marker.id));
      }

      const glMarker = new maplibregl.Marker({ element: el })
        .setLngLat([marker.longitude, marker.latitude])
        .setPopup(
          new maplibregl.Popup({ offset: 25 }).setHTML(
            `<div style="padding:8px;min-width:120px">
              <strong>${marker.label}</strong><br/>
              <small style="color:#666">${marker.status.replace(/_/g, " ")}</small>
            </div>`
          )
        )
        .addTo(map.current!);

      markersRef.current.push(glMarker);
    });

    // Fit bounds if markers exist
    if (markers.length > 1) {
      const bounds = new maplibregl.LngLatBounds();
      markers.forEach((m) => bounds.extend([m.longitude, m.latitude]));
      map.current?.fitBounds(bounds, { padding: 50 });
    }
  }, [markers]);

  return (
    <div
      ref={mapContainer}
      style={{ height, width: "100%", borderRadius: "12px", overflow: "hidden" }}
      className="border border-border/50"
    />
  );
}
