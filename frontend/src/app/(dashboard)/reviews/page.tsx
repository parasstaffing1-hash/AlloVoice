"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useAuth } from "@/lib/store";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";
import { Star, Quote } from "lucide-react";

export default function ReviewsPage() {
  const { token } = useAuth();
  const [reviews, setReviews] = useState<any[]>([]);

  useEffect(() => {
    if (!token) return;
    loadReviews();
  }, [token]);

  const loadReviews = async () => {
    try {
      const data: any = await api.reviews.list(token!);
      setReviews(data);
    } catch (e) {
      console.error(e);
    }
  };

  const averageRating =
    reviews.length > 0
      ? reviews.reduce((sum, r) => sum + r.rating, 0) / reviews.length
      : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Reviews</h1>
        <p className="text-muted-foreground">Customer feedback and ratings</p>
      </div>

      {reviews.length > 0 && (
        <Card>
          <CardContent className="p-6 flex items-center gap-6">
            <div className="text-center">
              <div className="text-5xl font-bold gradient-text">{averageRating.toFixed(1)}</div>
              <div className="flex items-center gap-1 mt-2">
                {[1, 2, 3, 4, 5].map((s) => (
                  <Star
                    key={s}
                    className={`h-4 w-4 ${
                      s <= averageRating ? "fill-yellow-400 text-yellow-400" : "text-muted-foreground"
                    }`}
                  />
                ))}
              </div>
              <p className="text-sm text-muted-foreground mt-1">{reviews.length} reviews</p>
            </div>
            <div className="flex-1 space-y-2">
              {[5, 4, 3, 2, 1].map((s) => {
                const count = reviews.filter((r) => r.rating === s).length;
                const pct = reviews.length > 0 ? (count / reviews.length) * 100 : 0;
                return (
                  <div key={s} className="flex items-center gap-2 text-sm">
                    <span className="w-8 text-right text-muted-foreground">{s}★</span>
                    <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                      <div
                        className="h-full bg-yellow-400 rounded-full"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                    <span className="w-8 text-muted-foreground">{count}</span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      <div className="space-y-4">
        {reviews.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">
              No reviews yet. Reviews will appear after completing jobs.
            </CardContent>
          </Card>
        ) : (
          reviews.map((review) => (
            <Card key={review.id} className="hover:border-primary/30 transition-all">
              <CardContent className="p-5">
                <div className="flex items-start gap-4">
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-yellow-500/10 shrink-0">
                    <Star className="h-5 w-5 text-yellow-400" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-0.5">
                        {[1, 2, 3, 4, 5].map((s) => (
                          <Star
                            key={s}
                            className={`h-3.5 w-3.5 ${
                              s <= review.rating
                                ? "fill-yellow-400 text-yellow-400"
                                : "text-muted-foreground"
                            }`}
                          />
                        ))}
                      </div>
                      <span className="text-sm text-muted-foreground">
                        {formatDateTime(review.created_at)}
                      </span>
                    </div>
                    {review.title && (
                      <h3 className="font-semibold mt-2">{review.title}</h3>
                    )}
                    {review.content && (
                      <p className="text-sm text-muted-foreground mt-1">{review.content}</p>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
