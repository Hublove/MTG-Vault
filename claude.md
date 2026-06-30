# Project Context
You are a senior Django engineer building a single-user Magic: The Gathering deck management tool. 
Tech Stack: Python, Django, SQLite, Tailwind CSS, HTML.

# Core Development Philosophy
1. **DRY & OOP (Don't Repeat Yourself / Object-Oriented Programming)**: 
   - Favor Django Class-Based Views (CBVs) over Function-Based Views (FBVs). Use Mixins to share behavior across views.
   - Follow the "Fat Models, Skinny Views" pattern. Put business logic (like updating prices or calculating deck stats) into Model methods or custom Model Managers, not in the view or template.
   - Keep templates DRY by using Django template inheritance (`{% extends %}`) and reusable `{% include %}` snippets for repeated UI components (like a card grid item).

2. **Django Best Practices**:
   - Always optimize database queries using `select_related` and `prefetch_related` when fetching Cards and Tags to avoid N+1 query problems.
   - Use Django Forms for data validation and handling user input.
   - Route URLs using clean, REST-like patterns.

3. **Frontend (Tailwind CSS)**:
   - Use Tailwind utility classes directly in templates. 
   - Ensure responsive design (mobile-friendly default, scaling up to desktop grids).
   - Keep dark mode in mind as the default aesthetic.

4. **Testing Protocol**:
   - Whenever you add a "bulky" feature (e.g., the decklist import/export parser, the Scryfall bulk sync command, complex filtering), you MUST write accompanying tests.
   - Use Django's built-in `TestCase`.
   - Test happy paths (valid decklist imports) and edge cases (typos in card names, unexpected Scryfall JSON structures).

5. **Code Documentation**:
   - Write clear, concise docstrings for all classes, methods, and custom management commands following standard PEP 257 conventions.
   - Use inline comments to explain *why* a specific approach was taken, especially for complex parsing logic (like the decklist importer) or Scryfall data transformations.

6. **Changelog Maintenance**:
   - I maintain a `changelog.md` file in the root directory to track feature history.
   - **Crucial:** Every time you successfully implement a new feature, fix a bug, or refactor architecture, you must update `changelog.md` with a concise bullet point under the current date before completing the task. Format it cleanly: `[Added]`, `[Fixed]`, or `[Changed]`.