"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import {
  Mic,
  MicOff,
  Send,
  Volume2,
  Loader2,
  Plus,
  Trash2,
  CheckCircle2,
  FileText,
  MessageSquare,
} from "lucide-react";

interface QuoteItem {
  description: string;
  quantity: number;
  unit_price: number;
}

export default function AIQuotePage() {
  const { token } = useAuth();
  const router = useRouter();
  const [isListening, setIsListening] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [textInput, setTextInput] = useState("");
  const [quoteItems, setQuoteItems] = useState<QuoteItem[]>([]);
  const [quoteTitle, setQuoteTitle] = useState("");
  const [total, setTotal] = useState(0);
  const [voiceResponse, setVoiceResponse] = useState("");
  const [step, setStep] = useState<"voice" | "review" | "sent">("voice");
  const [customers, setCustomers] = useState<any[]>([]);
  const [selectedCustomer, setSelectedCustomer] = useState<string>("");
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    if (!token) return;
    api.customers.list(token).then((data: any) => setCustomers(data)).catch(() => {});
  }, [token]);

  useEffect(() => {
    const t = quoteItems.reduce((sum, item) => sum + item.quantity * item.unit_price, 0);
    setTotal(t);
  }, [quoteItems]);

  const startListening = () => {
    if (!("webkitSpeechRecognition" in window) && !("SpeechRecognition" in window)) {
      alert("Speech recognition not supported. Please type your request.");
      return;
    }

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.lang = "en-GB";
    recognition.interimResults = true;
    recognition.continuous = false;

    recognition.onstart = () => setIsListening(true);

    recognition.onresult = (event: any) => {
      const result = event.results[event.results.length - 1];
      const text = result[0].transcript;
      setTranscript(text);
      if (result.isFinal) {
        setIsListening(false);
        processVoiceInput(text);
      }
    };

    recognition.onerror = () => setIsListening(false);
    recognition.onend = () => setIsListening(false);

    recognitionRef.current = recognition;
    recognition.start();
  };

  const stopListening = () => {
    recognitionRef.current?.stop();
    setIsListening(false);
  };

  const processVoiceInput = async (text: string) => {
    setIsProcessing(true);
    try {
      const result: any = await api.voice.transcribe({ transcript: text }, token!);
      setQuoteItems(result.quote_data.items || []);
      setQuoteTitle(result.quote_data.title || "Service Request");
      setVoiceResponse(result.voice_response || "");
      setTranscript(result.transcript || text);
      setStep("review");
    } catch (e) {
      console.error(e);
    }
    setIsProcessing(false);
  };

  const processTextInput = async () => {
    if (!textInput.trim()) return;
    setIsProcessing(true);
    try {
      const result: any = await api.voice.transcribe({ transcript: textInput }, token!);
      setQuoteItems(result.quote_data.items || []);
      setQuoteTitle(result.quote_data.title || "Service Request");
      setVoiceResponse(result.quote_response || "");
      setTranscript(textInput);
      setStep("review");
    } catch (e) {
      console.error(e);
    }
    setIsProcessing(false);
  };

  const updateItem = (index: number, field: keyof QuoteItem, value: any) => {
    const updated = [...quoteItems];
    (updated[index] as any)[field] = value;
    setQuoteItems(updated);
  };

  const addItem = () => {
    setQuoteItems([...quoteItems, { description: "", quantity: 1, unit_price: 0 }]);
  };

  const removeItem = (index: number) => {
    setQuoteItems(quoteItems.filter((_, i) => i !== index));
  };

  const createQuote = async () => {
    if (!selectedCustomer) {
      alert("Please select a customer");
      return;
    }
    try {
      await api.quotes.create(
        {
          job_id: "00000000-0000-0000-0000-000000000000",
          customer_id: selectedCustomer,
          title: quoteTitle,
          items: quoteItems,
          tax_rate: 20,
          notes: `AI-generated quote from voice input: "${transcript}"`,
        },
        token!
      );
      setStep("sent");
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold">AI Voice Quote</h1>
        <p className="text-muted-foreground">
          Describe the job in your voice or text — AI generates the quote
        </p>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-2">
        {["voice", "review", "sent"].map((s, i) => (
          <div key={s} className="flex items-center gap-2">
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold ${
                step === s
                  ? "bg-primary text-primary-foreground"
                  : ["voice", "review", "sent"].indexOf(step) > i
                  ? "bg-green-500/20 text-green-400"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {["voice", "review", "sent"].indexOf(step) > i ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : (
                i + 1
              )}
            </div>
            <span className="text-sm capitalize hidden sm:inline">
              {s === "voice" ? "Describe" : s === "review" ? "Review Quote" : "Done"}
            </span>
            {i < 2 && <div className="w-8 h-px bg-border hidden sm:block" />}
          </div>
        ))}
      </div>

      {/* Step 1: Voice Input */}
      {step === "voice" && (
        <Card>
          <CardContent className="p-8">
            <div className="text-center space-y-8">
              {/* Mic Button */}
              <div className="flex justify-center">
                <button
                  onClick={isListening ? stopListening : startListening}
                  disabled={isProcessing}
                  className={`relative flex h-32 w-32 items-center justify-center rounded-full transition-all ${
                    isListening
                      ? "bg-red-500/20 border-2 border-red-500 animate-pulse"
                      : "bg-primary/10 border-2 border-primary/30 hover:border-primary/60"
                  }`}
                >
                  {isProcessing ? (
                    <Loader2 className="h-12 w-12 text-primary animate-spin" />
                  ) : isListening ? (
                    <MicOff className="h-12 w-12 text-red-400" />
                  ) : (
                    <Mic className="h-12 w-12 text-primary" />
                  )}
                  {isListening && (
                    <div className="absolute inset-0 rounded-full border-2 border-red-500 animate-ping opacity-20" />
                  )}
                </button>
              </div>

              <div>
                <h2 className="text-xl font-semibold">
                  {isListening
                    ? "Listening... Speak now"
                    : isProcessing
                    ? "AI is generating your quote..."
                    : "Press to start speaking"}
                </h2>
                <p className="text-muted-foreground mt-2">
                  Works in English. Describe the job like you would to a customer.
                </p>
              </div>

              {/* Transcript Preview */}
              {transcript && (
                <div className="rounded-xl bg-background/50 border border-border/50 p-4 text-left max-w-lg mx-auto">
                  <p className="text-sm text-muted-foreground mb-1">Transcript:</p>
                  <p className="text-sm italic">"{transcript}"</p>
                </div>
              )}

              {/* Text Input Alternative */}
              <div className="border-t border-border/50 pt-6">
                <p className="text-sm text-muted-foreground mb-3">Or type your request:</p>
                <div className="flex gap-2 max-w-lg mx-auto">
                  <Input
                    placeholder="e.g., boiler repair, leaking radiator, combi boiler, Manchester M1..."
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && processTextInput()}
                    disabled={isProcessing}
                  />
                  <Button onClick={processTextInput} disabled={isProcessing || !textInput.trim()}>
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 2: Review Quote */}
      {step === "review" && (
        <div className="space-y-6">
          {/* Voice Response */}
          {voiceResponse && (
            <Card className="border-primary/30">
              <CardContent className="p-5">
                <div className="flex items-start gap-3">
                  <Volume2 className="h-5 w-5 text-primary mt-0.5 shrink-0" />
                  <div>
                    <p className="text-sm font-medium mb-1">AI Response:</p>
                    <p className="text-sm text-muted-foreground">{voiceResponse}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Quote Editor */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Quote Details</CardTitle>
                <Button variant="ghost" size="sm" onClick={() => setStep("voice")}>
                  Re-record
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <Input
                placeholder="Quote title"
                value={quoteTitle}
                onChange={(e) => setQuoteTitle(e.target.value)}
              />

              {/* Customer Selection */}
              <div>
                <label className="text-sm font-medium mb-2 block">Select Customer</label>
                <select
                  className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm"
                  value={selectedCustomer}
                  onChange={(e) => setSelectedCustomer(e.target.value)}
                >
                  <option value="">Select a customer...</option>
                  {customers.map((c: any) => (
                    <option key={c.id} value={c.id}>
                      {c.full_name} - {c.phone}
                    </option>
                  ))}
                </select>
              </div>

              {/* Line Items */}
              <div className="space-y-3">
                {quoteItems.map((item, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <Input
                      placeholder="Description"
                      value={item.description}
                      onChange={(e) => updateItem(i, "description", e.target.value)}
                      className="flex-1"
                    />
                    <Input
                      type="number"
                      placeholder="Qty"
                      value={item.quantity}
                      onChange={(e) => updateItem(i, "quantity", parseFloat(e.target.value) || 0)}
                      className="w-20"
                      min="0"
                    />
                    <Input
                      type="number"
                      placeholder="Price"
                      value={item.unit_price}
                      onChange={(e) => updateItem(i, "unit_price", parseFloat(e.target.value) || 0)}
                      className="w-28"
                      min="0"
                    />
                    <span className="text-sm font-medium w-24 text-right">
                      {formatCurrency(item.quantity * item.unit_price)}
                    </span>
                    <button
                      onClick={() => removeItem(i)}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                ))}
              </div>

              <Button variant="outline" size="sm" onClick={addItem} className="gap-1">
                <Plus className="h-3.5 w-3.5" />
                Add Item
              </Button>

              {/* Totals */}
              <div className="border-t border-border/50 pt-4 space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Subtotal</span>
                  <span>{formatCurrency(total)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">VAT (20%)</span>
                  <span>{formatCurrency(total * 0.2)}</span>
                </div>
                <div className="flex justify-between text-lg font-bold border-t border-border/50 pt-2">
                  <span>Total</span>
                  <span className="gradient-text">{formatCurrency(total * 1.2)}</span>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Actions */}
          <div className="flex gap-3">
            <Button onClick={createQuote} className="flex-1 gap-2" disabled={!selectedCustomer}>
              <FileText className="h-4 w-4" />
              Create Quote
            </Button>
            <Button variant="outline" onClick={() => setStep("voice")}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {/* Step 3: Sent */}
      {step === "sent" && (
        <Card>
          <CardContent className="py-12 text-center space-y-4">
            <div className="flex justify-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-green-500/20">
                <CheckCircle2 className="h-8 w-8 text-green-400" />
              </div>
            </div>
            <h2 className="text-2xl font-bold">Quote Created!</h2>
            <p className="text-muted-foreground">
              Your quote has been created and sent to the customer.
            </p>
            <div className="flex justify-center gap-3 pt-4">
              <Button onClick={() => { setStep("voice"); setQuoteItems([]); setTranscript(""); }}>
                Create Another
              </Button>
              <Button variant="outline" onClick={() => router.push("/quotes")}>
                View All Quotes
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
