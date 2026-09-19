"use client";

import { useState, useEffect, useRef } from "react";
import { Input } from "@/components/ui/input";
import { CheckCircle2, MapPin, Loader2 } from "lucide-react";

interface PostcodeResult {
  postcode: string;
  latitude: number;
  longitude: number;
  region: string;
  admin_district: string;
  country: string;
}

interface PostcodeAutocompleteProps {
  onSelect: (result: PostcodeResult) => void;
  placeholder?: string;
  className?: string;
}

export default function PostcodeAutocomplete({
  onSelect,
  placeholder = "Enter UK postcode (e.g., M1 1AE)",
  className,
}: PostcodeAutocompleteProps) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(false);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (query.length < 2 || selected) {
      setSuggestions([]);
      return;
    }

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await fetch(
          `https://api.postcodes.io/postcodes/${encodeURIComponent(query)}/autocomplete`
        );
        const data = await res.json();
        setSuggestions(data.result || []);
      } catch {
        setSuggestions([]);
      }
      setLoading(false);
    }, 300);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, selected]);

  const handleSelect = async (postcode: string) => {
    setQuery(postcode);
    setSelected(true);
    setSuggestions([]);
    setLoading(true);

    try {
      const cleanPostcode = postcode.replace(/\s/g, "");
      const res = await fetch(`https://api.postcodes.io/postcodes/${cleanPostcode}`);
      const data = await res.json();
      if (data.result) {
        onSelect({
          postcode: data.result.postcode,
          latitude: data.result.latitude,
          longitude: data.result.longitude,
          region: data.result.region,
          admin_district: data.result.admin_district,
          country: data.result.country,
        });
      }
    } catch {
      // Fallback: use the query as-is
    }
    setLoading(false);
  };

  const handleChange = (value: string) => {
    setSelected(false);
    setQuery(value.toUpperCase());
  };

  return (
    <div className={`relative ${className || ""}`}>
      <div className="relative">
        <MapPin className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(e) => handleChange(e.target.value)}
          placeholder={placeholder}
          className="pl-9 pr-9"
          maxLength={8}
        />
        {loading && (
          <Loader2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-muted-foreground" />
        )}
        {selected && !loading && (
          <CheckCircle2 className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-green-500" />
        )}
      </div>

      {suggestions.length > 0 && !selected && (
        <div className="absolute z-50 mt-1 w-full rounded-lg border border-border bg-card shadow-xl max-h-60 overflow-auto">
          {suggestions.slice(0, 8).map((postcode) => (
            <button
              key={postcode}
              onClick={() => handleSelect(postcode)}
              className="flex w-full items-center gap-2 px-4 py-2.5 text-sm hover:bg-accent transition-colors text-left"
            >
              <MapPin className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              {postcode}
            </button>
          ))}
        </div>
      )}

      {query && !selected && suggestions.length === 0 && !loading && query.length >= 2 && (
        <p className="mt-1 text-xs text-muted-foreground">
          Press Enter or select from suggestions
        </p>
      )}
    </div>
  );
}
