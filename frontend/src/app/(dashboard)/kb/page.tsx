"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { BookOpen, Plus, Search as SearchIcon, Eye } from "lucide-react";

export default function KnowledgeBasePage() {
  const { token } = useAuth();
  const [articles, setArticles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!token) return;
    api.knowledgeBase.list(token)
      // Backend returns a bare array (GET /api/kb/).
      .then((r: any) => setArticles(Array.isArray(r) ? r : r.articles || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  const categories = [...new Set(articles.map((a) => a.category).filter(Boolean))];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Knowledge Base</h1>
        <Button className="gap-2"><Plus className="h-4 w-4" />New Article</Button>
      </div>

      <div className="relative">
        <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input className="pl-9" placeholder="Search articles..." value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      {categories.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {categories.map((cat) => (
            <Badge key={cat} variant="outline">{cat}</Badge>
          ))}
        </div>
      )}

      {loading ? (
        <p className="text-muted-foreground">Loading...</p>
      ) : articles.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center">
            <BookOpen className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium">No articles yet</h3>
            <p className="text-sm text-muted-foreground mt-1">
              Create guides and standard operating procedures for your team
            </p>
            <Button className="mt-4 gap-2"><Plus className="h-4 w-4" />Create Article</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {articles
            .filter((a) => !search || a.title.toLowerCase().includes(search.toLowerCase()))
            .map((a) => (
            <Card key={a.id} className="hover:border-primary/50 cursor-pointer transition-colors">
              <CardContent className="space-y-2">
                <div className="flex items-center justify-between">
                  <p className="font-medium">{a.title}</p>
                  {a.category && <Badge variant="outline" className="text-xs">{a.category}</Badge>}
                </div>
                <p className="text-sm text-muted-foreground line-clamp-2">{a.content?.slice(0, 120)}...</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
