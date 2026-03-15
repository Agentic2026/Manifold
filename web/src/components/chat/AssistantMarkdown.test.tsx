import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AssistantMarkdown } from "./AssistantMarkdown";

describe("AssistantMarkdown", () => {
  it("renders with data-testid attribute", () => {
    render(<AssistantMarkdown markdown="Hello" />);
    expect(screen.getByTestId("assistant-markdown")).toBeInTheDocument();
  });

  it("renders headings", () => {
    const { container } = render(
      <AssistantMarkdown markdown="# Heading 1\n\n## Heading 2\n\n### Heading 3" />,
    );
    expect(container.textContent).toContain("Heading 1");
    expect(container.textContent).toContain("Heading 2");
    expect(container.textContent).toContain("Heading 3");
    // Raw markdown syntax should not leak
    expect(container.textContent).not.toMatch(/^#{1,3}\s/m);
  });

  it("renders bold text", () => {
    const { container } = render(
      <AssistantMarkdown markdown="This is **bold** text" />,
    );
    expect(container.textContent).toContain("bold");
    expect(container.textContent).toContain("text");
  });

  it("renders inline code", () => {
    const { container } = render(
      <AssistantMarkdown markdown="Use `console.log()` here" />,
    );
    expect(container.textContent).toContain("console.log()");
  });

  it("renders a list", () => {
    const { container } = render(
      <AssistantMarkdown markdown={"- Item one\n- Item two\n- Item three"} />,
    );
    expect(container.textContent).toContain("Item one");
    expect(container.textContent).toContain("Item two");
    expect(container.textContent).toContain("Item three");
  });

  it("renders thematic breaks without raw ---", () => {
    const { container } = render(
      <AssistantMarkdown markdown={"Above\n\n---\n\nBelow"} />,
    );
    expect(container.textContent).toContain("Above");
    expect(container.textContent).toContain("Below");
    // The --- should be rendered as an <hr>, not raw text
    expect(container.innerHTML).toContain("<hr");
  });

  it("does not crash on incomplete markdown while streaming", () => {
    const { container } = render(
      <AssistantMarkdown
        markdown={"**unclosed bold\n```\nunclosed code"}
        isStreaming={true}
      />,
    );
    expect(container.textContent).toContain("unclosed bold");
    expect(container.textContent).toContain("unclosed code");
  });

  it("does not crash on empty markdown", () => {
    render(<AssistantMarkdown markdown="" />);
    expect(screen.getByTestId("assistant-markdown")).toBeInTheDocument();
  });
});
