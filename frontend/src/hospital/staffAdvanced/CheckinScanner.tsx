
import { useEffect, useRef, useState } from "react";
import { parseCheckinQr, type ScannedCheckin } from "./utils";

interface BarcodeResult {
  rawValue: string;
}

interface BarcodeDetectorLike {
  detect(source: HTMLVideoElement): Promise<BarcodeResult[]>;
}

interface BarcodeDetectorConstructor {
  new (options: { formats: string[] }): BarcodeDetectorLike;
}

type BarcodeWindow = Window & { BarcodeDetector?: BarcodeDetectorConstructor };

export function CheckinScanner({
  disabled,
  onScan,
}: {
  disabled?: boolean;
  onScan: (result: ScannedCheckin) => void;
}) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const onScanRef = useRef(onScan);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);
  const [active, setActive] = useState(false);
  const [starting,setStarting] = useState(false);
  const mountedRef = useRef(true);
  const generationRef = useRef(0);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [scannerMessage, setScannerMessage] = useState("");

  onScanRef.current = onScan;

  function stopCamera() {
    generationRef.current += 1;
    setStarting(false);
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    timerRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setStream(null);
    setActive(false);
  }

  async function startCamera() {
    if(starting || active || disabled)return;
    const generation=++generationRef.current;
    setStarting(true);
    const Detector = (window as BarcodeWindow).BarcodeDetector;
    if (!navigator.mediaDevices?.getUserMedia) {
      setStarting(false);
      setScannerMessage("QR scanning is unavailable in this browser. Enter the appointment ID and token below.");
      return;
    }
    try {
      const reader = Detector ? null : new (await import("@zxing/browser")).BrowserQRCodeReader();
      const scanner: BarcodeDetectorLike = Detector ? new Detector({ formats: ["qr_code"] }) : {
        async detect(video) {
          const canvas = document.createElement("canvas");
          canvas.width = video.videoWidth; canvas.height = video.videoHeight;
          const context = canvas.getContext("2d");
          if (!context || !canvas.width || !canvas.height) return [];
          context.drawImage(video, 0, 0);
          try { return [{ rawValue: reader!.decodeFromCanvas(canvas).getText() }]; }
          catch { return []; } // A frame without a readable code keeps scanning.
        },
      };
      const camera = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      if(!mountedRef.current || generation!==generationRef.current){camera.getTracks().forEach(track=>track.stop());return;}
      setStarting(false);
      streamRef.current = camera;
      setStream(camera);
      setActive(true);
      setScannerMessage("Point the camera at the patient's check-in QR code.");
      detectorRef.current = scanner;
    } catch {
      if(!mountedRef.current || generation!==generationRef.current)return;
      stopCamera();
      setScannerMessage("Camera access is unavailable. Enter the appointment ID and token below.");
    }
  }

  const detectorRef = useRef<BarcodeDetectorLike | null>(null);

  useEffect(() => {
    if (!stream || !videoRef.current) return;
    const video = videoRef.current;
    let disposed = false;
    video.srcObject = stream;
    void video.play().catch(() => {
      if (!disposed) {
        stopCamera();
        setScannerMessage("Camera playback is unavailable. Enter the appointment ID and token below.");
      }
    });

    const detect = async () => {
      if (disposed || !videoRef.current || !detectorRef.current) return;
      if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        try {
          const results = await detectorRef.current.detect(video);
          const rawValue = results.find((result) => result.rawValue)?.rawValue;
          if (rawValue) {
            try {
              const scanned = parseCheckinQr(rawValue);
              stopCamera();
              onScanRef.current(scanned);
              setScannerMessage("QR code read. Review the appointment and confirm check-in below.");
              return;
            } catch (error) {
              stopCamera();
              setScannerMessage(error instanceof Error ? error.message : "This QR code could not be read.");
              return;
            }
          }
        } catch {
          stopCamera();
          setScannerMessage("QR scanning stopped. Enter the appointment ID and token below.");
          return;
        }
      }
      timerRef.current = window.setTimeout(() => void detect(), 250);
    };

    void detect();
    return () => {
      disposed = true;
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = null;
      video.srcObject = null;
    };
  }, [stream]);

  useEffect(() => {mountedRef.current=true;return () => {
    mountedRef.current=false;generationRef.current+=1;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
  };}, []);

  return (
    <div className="staff-advanced-scanner">
      <p>
        Camera access starts only when you request scanning. The token stays in this page's memory and is cleared after a confirmed check-in.
      </p>
      {active && <video aria-label="Check-in QR camera" autoPlay muted playsInline ref={videoRef} />}
      {scannerMessage && <p role="status">{scannerMessage}</p>}
      {active ? (
        <button type="button" disabled={disabled} onClick={stopCamera}>Stop QR scanner</button>
      ) : (
        <button type="button" disabled={disabled || starting} onClick={() => void startCamera()}>{starting ? "Opening camera…" : "Scan check-in QR"}</button>
      )}
    </div>
  );
}
