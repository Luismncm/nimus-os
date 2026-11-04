"""NIMUS OS in the cloud: sign-in and the HTTP routes the Next.js app calls.

Lives outside api/ on purpose: Vercel turns every file in api/ into its own function, and the whole API is
one function (api/index.py) that imports from here.
"""
