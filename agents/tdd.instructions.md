# Test-Driven Development (TDD) Instructions







## Core Principle







**Write the test FIRST, then write the code to make it pass.**







This applies to ALL development work:



- New features



- Bug fixes



- Refactoring



- Code improvements







## The Red-Green-Refactor Cycle







### 1. 🔴 RED - Write a Failing Test



**BEFORE writing any implementation code:**



1. Understand the requirement or bug



2\. Write a test that describes the desired behavior



3\. Run the test - it MUST fail (because implementation doesn't exist yet)



4\. Verify it fails for the RIGHT reason (not syntax errors)



&nbsp;



\*\*Why this matters:\*\*



\- Proves the test can detect the problem



\- Ensures you're testing the right thing



\- Prevents false positives (tests that always pass)



&nbsp;



\### 2. 🟢 GREEN - Write Minimal Code to Pass



1\. Write the SIMPLEST code that makes the test pass



2\. No over-engineering, no premature optimization



3\. Run the test - it should now pass



4\. If it doesn't pass, debug until it does



&nbsp;



\*\*Why this matters:\*\*



\- Keeps implementation focused



\- Prevents scope creep



\- Reduces unnecessary complexity



&nbsp;



\### 3. ♻️ REFACTOR - Improve the Code



\*\*Only after tests are passing:\*\*



1\. Clean up the code (DRY, naming, structure)



2\. Run tests after each change - they must stay green



3\. Stop when code is clean and tests still pass



&nbsp;



\*\*Why this matters:\*\*



\- Refactoring is safe when tests are green



\- Improves maintainability without breaking behavior



\- Tests act as a safety net



&nbsp;



\## TDD Workflow Steps



&nbsp;



\### For New Features



&nbsp;



\*\*Step 1: Break down the feature\*\*



\- Identify smallest testable behaviors



\- List test cases needed (see jest-unit-tests.instructions.md)



\- Prioritize: happy path → error cases → edge cases



&nbsp;



\*\*Step 2: Write first test (RED)\*\*



```javascript



describe('FeatureName', () => {



&nbsp; it('should return expected result for valid input', () => {



&nbsp;   // Arrange



&nbsp;   const input = validInput;



&nbsp;  



&nbsp;   // Act



&nbsp;   const result = featureFunction(input);



&nbsp;  



&nbsp;   // Assert



&nbsp;   expect(result).toEqual(expectedOutput);



&nbsp; });



});



```



\- Run test → verify it fails



\- Commit message: `test: add test for feature X happy path`



&nbsp;



\*\*Step 3: Implement minimal code (GREEN)\*\*



\- Write simplest implementation to pass the test



\- Run test → verify it passes



\- Commit message: `feat: implement feature X happy path`



&nbsp;



\*\*Step 4: Refactor (if needed)\*\*



\- Clean up code while keeping tests green



\- Run tests after each change



\- Commit message: `refactor: improve feature X implementation`



&nbsp;



\*\*Step 5: Repeat for next test case\*\*



\- Write next test (error case, edge case, etc.)



\- Go back to Step 2



&nbsp;



\### For Bug Fixes



&nbsp;



\*\*Step 1: Reproduce the bug with a test\*\*



```javascript



it('should handle edge case that causes bug', () => {



&nbsp; const buggyInput = reproduceBugInput;



&nbsp;



&nbsp; // This test should FAIL initially (proving the bug exists)



&nbsp; expect(() => buggyFunction(buggyInput)).not.toThrow();



&nbsp; expect(buggyFunction(buggyInput)).toEqual(correctOutput);



});



```



\- Run test → verify it fails (confirms bug exists)



\- Commit message: `test: reproduce bug with input X`



&nbsp;



\*\*Step 2: Fix the bug\*\*



\- Modify code to pass the test



\- Run test → verify it passes



\- Run ALL tests → ensure no regressions



\- Commit message: `fix: handle edge case X correctly`



&nbsp;



\*\*Step 3: Add related tests\*\*



\- Consider similar edge cases



\- Add tests for related scenarios



\- Follow RED-GREEN-REFACTOR for each



&nbsp;



\### For Refactoring



&nbsp;



\*\*Step 1: Ensure existing tests are comprehensive\*\*



\- Review test coverage



\- Add missing tests FIRST if needed



\- All tests must be green before refactoring



&nbsp;



\*\*Step 2: Refactor in small steps\*\*



\- Make one small change



\- Run tests → must stay green



\- Commit after each successful change



\- Commit message: `refactor: extract method X` or `refactor: simplify logic in Y`



&nbsp;



\*\*Step 3: If tests fail during refactor\*\*



\- Either: revert the change



\- Or: fix the implementation (not the test)



\- Never change tests to match broken code



&nbsp;



\## Critical Rules



&nbsp;



\### ❌ NEVER Do This



\- Write implementation before tests



\- Change tests to make them pass (unless test was wrong)



\- Skip tests "just this once"



\- Write tests after implementation is complete



\- Commit code without tests



\- Disable or comment out failing tests



&nbsp;



\### ✅ ALWAYS Do This



\- Write test FIRST



\- Run tests frequently (after each change)



\- Keep tests fast (mock external dependencies)



\- Make small commits (test + implementation pairs)



\- Ensure tests fail for the right reason



\- Fix code to pass tests, not vice versa



&nbsp;



\## Test Quality Standards



&nbsp;



\### Each Test Must Be:



1\. \*\*Isolated\*\* - No dependencies on other tests or execution order



2\. \*\*Deterministic\*\* - Same input = same result, every time



3\. \*\*Fast\*\* - Mock external I/O (network, database, filesystem, AWS)



4\. \*\*Readable\*\* - Clear naming, AAA structure (Arrange-Act-Assert)



5\. \*\*Focused\*\* - Test one behavior per test



&nbsp;



\### Test Coverage Requirements



\- \*\*Happy path\*\* - Normal, expected usage



\- \*\*Error cases\*\* - How failures are handled



\- \*\*Edge cases\*\* - Boundaries, empty values, null/undefined



\- \*\*Side effects\*\* - Verify logging, metrics, external calls



&nbsp;



See \[Jest Unit Tests Instructions](./jest-unit-tests.instructions.md) for detailed testing patterns.



&nbsp;



\## Common TDD Patterns



&nbsp;



\### Pattern 1: Outside-In (Behavior-First)



1\. Start with highest-level behavior (API endpoint, CLI command)



2\. Write test for expected behavior



3\. Implement by driving out lower-level components



4\. Mock dependencies until ready to implement them



&nbsp;



\### Pattern 2: Inside-Out (Unit-First)



1\. Start with lowest-level utilities/functions



2\. Build up to higher-level components



3\. Each layer is fully tested before building next layer



&nbsp;



\*\*Choose based on context:\*\*



\- Outside-In: When requirements are clear, complex systems



\- Inside-Out: When building libraries, reusable utilities



&nbsp;



\## TDD Benefits Checklist



&nbsp;



After following TDD, you should have:



\- ✅ Tests that document expected behavior



\- ✅ Code that does exactly what's needed (no more, no less)



\- ✅ Confidence to refactor without breaking things



\- ✅ Fast feedback loop (minutes, not hours)



\- ✅ Fewer bugs in production



\- ✅ Better design (testable code is usually better code)



&nbsp;



\## Integration with Git Workflow



&nbsp;



\### Commit Strategy



\*\*Minimum 2 commits per feature:\*\*



1\. `test: add test for <behavior>`



2\. `feat: implement <behavior>`



3\. (Optional) `refactor: improve <implementation>`



&nbsp;



\*\*Each commit should:\*\*



\- Have passing tests (green state)



\- Build successfully



\- Be deployable (if on shared branch)



&nbsp;



\### Before Creating PR



1\. All tests must be green



2\. No skipped/disabled tests (unless documented reason)



3\. Test coverage meets project standards



4\. Tests run fast (< 1s per test file for unit tests)



&nbsp;



\## Handling Legacy Code



&nbsp;



When working with code that has no tests:



&nbsp;



\*\*Step 1: Characterization tests\*\*



\- Write tests describing CURRENT behavior (even if wrong)



\- These tests preserve existing behavior



&nbsp;



\*\*Step 2: Add test for desired behavior\*\*



\- Write test for what SHOULD happen



\- This test will fail initially



&nbsp;



\*\*Step 3: Fix code\*\*



\- Modify implementation



\- New test passes



\- Characterization tests may fail (that's OK if behavior changed intentionally)



&nbsp;



\*\*Step 4: Update or remove characterization tests\*\*



\- Update them if behavior change is intentional



\- Keep them if behavior should be preserved



&nbsp;



\## Troubleshooting



&nbsp;



\### "I don't know what test to write"



→ Start with the simplest case: "given valid input, returns expected output"



&nbsp;



\### "My test is too complicated"



→ Your design might be too complex - refactor to smaller functions



&nbsp;



\### "I need to mock too many things"



→ High coupling - consider dependency injection or simpler interfaces



&nbsp;



\### "Tests are slow"



→ You're testing too much at once - break into smaller unit tests



&nbsp;



\### "Test passes but code is wrong"



→ Test isn't specific enough - add more assertions or edge cases



&nbsp;



\## Remember



&nbsp;



\*\*TDD is not about testing, it's about design.\*\*



&nbsp;



Writing tests first forces you to:



\- Think about interfaces before implementation



\- Write testable (and therefore better) code



\- Create minimal, focused solutions



\- Build confidence in your changes



&nbsp;



\*\*When in doubt: RED → GREEN → REFACTOR\*\*

