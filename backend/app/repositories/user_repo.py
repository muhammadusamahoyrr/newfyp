import re

from pymongo import ASCENDING, DESCENDING

from app.db.collections import get_users_col
from app.repositories.base import BaseRepository
from app.schemas.common import PaginatedResponse


def lawyer_profile_complete(lawyer: dict | None) -> bool:
    """The completeness half of `UserRepository.lawyer_filter`, for a document
    already in hand: a non-blank bar number and at least one practice area.
    With LAWYER_AUTO_APPROVE approval comes before onboarding, so every path
    that offers a lawyer to a client checks this as well as kyc_verified."""
    lp = (lawyer or {}).get("lawyer_profile") or {}
    bar = lp.get("bar_number")
    return isinstance(bar, str) and bool(bar.strip()) and bool(lp.get("specializations"))


class UserRepository(BaseRepository):
    def __init__(self):
        super().__init__(get_users_col)  # pass accessor, not result

    async def find_by_email(self, email: str) -> dict | None:
        return await self.find_one({"email": email.lower()})

    async def find_by_id(self, user_id: str) -> dict | None:
        return await self.find_one({"_id": user_id})

    # Directory sort keys. The client picks one by name; the server owns what
    # each means, so an arbitrary field can never be sorted on from outside.
    #
    # Every key ends with `_id` ASC. That tiebreaker is not decoration: MongoDB
    # gives no stable order for documents that tie on the sort field, so with
    # (say) nine lawyers all rated 4.0, "page 2" could re-show a lawyer already
    # seen on page 1 and silently skip another entirely. Paging a non-unique
    # sort without a tiebreaker loses records.
    LAWYER_SORTS: dict[str, list[tuple]] = {
        "rating_desc":     [("lawyer_profile.rating", DESCENDING), ("_id", ASCENDING)],
        "rating_asc":      [("lawyer_profile.rating", ASCENDING), ("_id", ASCENDING)],
        # Missing `hourly_rate` sorts FIRST ascending and LAST descending, which
        # is MongoDB's own ordering for absent fields. The alternative — hiding
        # unpriced lawyers from a price sort — would remove real people from the
        # directory for not having filled in one optional field.
        "fee_asc":         [("lawyer_profile.hourly_rate", ASCENDING), ("_id", ASCENDING)],
        "fee_desc":        [("lawyer_profile.hourly_rate", DESCENDING), ("_id", ASCENDING)],
        "experience_desc": [("lawyer_profile.experience_years", DESCENDING), ("_id", ASCENDING)],
        "name_asc":        [("full_name", ASCENDING), ("_id", ASCENDING)],
        "name_desc":       [("full_name", DESCENDING), ("_id", ASCENDING)],
    }

    @staticmethod
    def lawyer_filter(
        province: str | None = None,
        case_type: str | None = None,
        min_rating: float = 0.0,
        availability: bool | None = None,
        include_federal: bool = False,
        q: str | None = None,
        bar_number: str | None = None,
        specialization: str | None = None,
    ) -> dict:
        """The Mongo filter for verified, active lawyers (see find_lawyers).

        Shared by the directory list and its counts so the two can never
        disagree about who matches a filter."""
        query: dict = {
            "role": "lawyer",
            "lawyer_profile.kyc_verified": True,
            "is_active": True,
            # Profile completeness. With LAWYER_AUTO_APPROVE an account is
            # approved at sign-up, before onboarding, so approval alone no
            # longer means there is a profile to show. Kept under `$and` so
            # the bar-number search and the practice-area filter below can
            # still set their own keys on the same fields.
            "$and": [
                {"lawyer_profile.bar_number": {"$type": "string", "$regex": r"\S"}},
                {"lawyer_profile.specializations.0": {"$exists": True}},
            ],
        }
        if min_rating > 0:
            # Applied ONLY when it filters something. `{"$gte": 0.0}` looks
            # inert and is not: in MongoDB a document whose
            # `lawyer_profile.rating` key is ABSENT does not satisfy `$gte`, so
            # an unrated lawyer was excluded from search, from the match pool
            # and from the general listing at once — the client was told no
            # verified lawyers existed while one sat in the collection.
            query["lawyer_profile.rating"] = {"$gte": min_rating}
        if province and not (include_federal and province == "federal"):
            # The omitted case is a federal matter under the matcher's rules:
            # every province is eligible, so no province clause is added at all.
            query["province"] = (
                {"$in": [province, "federal"]} if include_federal else province
            )
        areas = [a for a in (case_type, specialization) if a]
        if len(areas) == 1:
            query["lawyer_profile.specializations"] = areas[0]
        elif areas:
            query["lawyer_profile.specializations"] = {"$all": areas}
        if availability is not None:
            query["lawyer_profile.availability"] = availability

        # ── Text search ──────────────────────────────────────────────────────
        # Escaped, because the needle is a user's raw keystrokes. Unescaped it
        # is a regular expression: "a|b" would silently widen the search and a
        # nested quantifier could hang the query on a large collection.
        if q and q.strip():
            needle = re.escape(q.strip())
            query["$and"] = query.get("$and", []) + [{"$or": [
                {"full_name": {"$regex": needle, "$options": "i"}},
                {"province": {"$regex": needle, "$options": "i"}},
                {"lawyer_profile.specializations": {"$regex": needle, "$options": "i"}},
            ]}]
        if bar_number and bar_number.strip():
            query["lawyer_profile.bar_number"] = {
                "$regex": re.escape(bar_number.strip()), "$options": "i"}

        return query

    async def count_lawyers(self, **filters) -> int:
        """How many lawyers match `lawyer_filter(**filters)`."""
        return await self.count(self.lawyer_filter(**filters))

    async def find_lawyers(
        self,
        province: str | None = None,
        case_type: str | None = None,
        min_rating: float = 0.0,
        availability: bool | None = None,
        page: int = 1,
        page_size: int = 10,
        include_federal: bool = False,
        q: str | None = None,
        bar_number: str | None = None,
        sort: str | None = None,
        specialization: str | None = None,
    ) -> PaginatedResponse:
        """Verified, active lawyers, optionally narrowed.

        `specialization` is one practice area the lawyer lists (property,
        corporate, tax…); with `case_type` too, the lawyer must list both.

        `include_federal` makes the province filter match what the MATCHER
        means by province, rather than what a directory filter means. It is off
        by default because a client who filters the directory to "Punjab" means
        Punjab; the matcher must have it on, because `query_similar_lawyers` has
        always been wider than this and the two candidate pools — whose whole
        purpose is to cover for each other — must agree about who exists.

        With it on:

          provincial matter -> that province PLUS `federal`
              A nationwide advocate is available in every province. With this
              off they were reachable through neither pool if they had no
              vector, so they were invisible for every provincial case.

          federal matter    -> NO province filter at all
              Eligibility is deliberately NOT narrowed to `federal` lawyers.
              Enrolment is not something this system can verify, and several of
              its own federal-forum case types (FIA cybercrime among them) are
              routinely handled by provincially enrolled advocates — so
              excluding them would be a guess at a bar rule, made by a filter,
              that silently hides the right lawyer.

              Ranking carries the distinction instead: `_score_lawyer` awards
              its 0.17 province weight on a federal matter only to a lawyer
              whose own province is `federal`, so a nationwide advocate leads
              and a provincial specialist stays reachable behind them. This is
              the same move the module already made once — see the
              `_score_lawyer` docstring on province having been "a filter and
              nothing more, so it could not affect an ordering, only
              membership".
        """
        query = self.lawyer_filter(
            province=province, case_type=case_type, min_rating=min_rating,
            availability=availability, include_federal=include_federal,
            q=q, bar_number=bar_number, specialization=specialization,
        )
        return await self.paginate(
            query,
            page=page,
            page_size=page_size,
            sort=self.LAWYER_SORTS.get(sort or "", self.LAWYER_SORTS["rating_desc"]),
        )

    async def recompute_rating(self, lawyer_id: str) -> dict:
        """Recalculate a lawyer's rating FROM the reviews themselves.

        Replaces an incremental update that read the current aggregate, added
        one review to it, and wrote the result back. That was correct only if it
        ran exactly once per review, and `submit_review` could not promise that:
        it inserted the review first (so the unique index rejects a duplicate
        before the aggregate is touched) and updated the rating second. If the
        second write failed, the review existed, the rating did not reflect it,
        and every retry was refused as a duplicate — leaving the aggregate
        permanently wrong with no way to repair it through the API.

        Deriving the value instead of accumulating it removes the failure mode
        rather than narrowing it:

          * idempotent — running it twice, or a hundred times, is the same as
            running it once, so a retry is always safe;
          * order-independent — it does not matter whether it runs before or
            after the insert, or how many times;
          * self-healing — it repairs drift that already exists, including from
            reviews written before this function did.

        Deliberately NOT a MongoDB transaction. Transactions need a replica set:
        Atlas has one, a developer's local mongod does not, so that version
        would take a path in production that no test ever executes — a worse
        trap than the bug. This behaves identically everywhere.

        The cost is an aggregation over one lawyer's reviews per call, served by
        the existing `lawyer_id` index. A lawyer has tens of reviews, not
        millions.

        Returns the aggregate it wrote.
        """
        from app.db.collections import get_lawyer_reviews_col

        cursor = get_lawyer_reviews_col().aggregate([
            {"$match": {"lawyer_id": lawyer_id}},
            {"$group": {"_id": None,
                        "avg": {"$avg": "$stars"},
                        "n": {"$sum": 1}}},
        ])
        rows = [row async for row in cursor]

        # No reviews is a real state, not a missing one: a lawyer whose only
        # review is withdrawn must go back to 0.0/0, not keep a stale average.
        if rows:
            rating = round(float(rows[0].get("avg") or 0.0), 2)
            total = int(rows[0].get("n") or 0)
        else:
            rating, total = 0.0, 0

        await self.update_one(
            {"_id": lawyer_id},
            {"$set": {
                "lawyer_profile.rating": rating,
                "lawyer_profile.total_reviews": total,
            }},
        )
        return {"rating": rating, "total_reviews": total}

    async def find_reviews(
        self, lawyer_id: str, page: int = 1, page_size: int = 10
    ) -> PaginatedResponse:
        """One page of a lawyer's reviews, newest first."""
        from app.db.collections import get_lawyer_reviews_col
        from app.repositories.base import BaseRepository

        class _Reviews(BaseRepository):
            def __init__(self):
                super().__init__(get_lawyer_reviews_col)

        return await _Reviews().paginate(
            {"lawyer_id": lawyer_id},
            page=page,
            page_size=page_size,
            sort=[("created_at", DESCENDING)],
        )
