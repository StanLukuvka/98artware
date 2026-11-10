"""art98 in a container: the image, the stage server inside it, and the host's end of it.

serve.py runs inside the container. host.py runs on the host: it builds and starts
containers, and gives `art98.session.boot(backend="container")` its Session.
"""
