from graphviz import Digraph
import base64


from graphviz import Digraph
import base64


def generate_image_base64(roadmap):
    if "roadmap" not in roadmap or "stages" not in roadmap["roadmap"]:
        return None

    stages = roadmap["roadmap"]["stages"]

    # Global graph style
    dot = Digraph(comment="Learning Roadmap", format="png")
    dot.attr(rankdir="LR", bgcolor="white")  # left-to-right layout

    # Node defaults
    dot.attr(
        "node",
        shape="rectangle",
        style="rounded,filled",
        fillcolor="lightgoldenrod1",
        color="gray30",
        fontname="Helvetica",
        fontsize="12",
    )

    # Edge defaults
    dot.attr(
        "edge",
        color="gray40",
        arrowsize="0.8",
        penwidth="1.2",
        fontname="Helvetica",
        fontsize="10",
    )

    for stage in stages:
        title = stage.get("title", "")
        goal = stage.get("goal", "")
        duration = stage.get("duration", "")
        topics = "\n".join(stage.get("topics", []))
        resources = "\n".join(
            [f"• {r['title']} ({r['type']})" for r in stage.get("resources", [])]
        )

        # Use bold for title
        label = (
            f"<<B>{title}</B><BR/><BR/>"
            f"<I>Goal:</I> {goal}<BR/>"
            f"<I>Duration:</I> {duration}<BR/><BR/>"
            f"<U>Topics</U><BR ALIGN='LEFT'/>{topics.replace(chr(10), '<BR/>')}<BR/><BR/>"
            f"<U>Resources</U><BR ALIGN='LEFT'/>{resources.replace(chr(10), '<BR/>')}>"
        )

        dot.node(stage["id"], label=label)

    for i in range(len(stages) - 1):
        dot.edge(stages[i]["id"], stages[i + 1]["id"], label="next")

    img_bytes = dot.pipe(format="png")

    return base64.b64encode(img_bytes).decode("utf-8")
