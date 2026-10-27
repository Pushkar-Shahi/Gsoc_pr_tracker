"""
Google Summer of Code (GSoC) Organization Registry & Matcher.
Contains verified participating umbrella and individual organizations across GSoC history.
"""

from typing import Optional, Dict

GSOC_ORGS_MAP: Dict[str, str] = {
    # Python & Scientific Python Ecosystem
    "psf": "Python Software Foundation",
    "python": "Python Software Foundation",
    "pallets": "Pallets / PSF (Flask, Click, Jinja)",
    "tiangolo": "FastAPI / Python",
    "celery": "Celery / PSF",
    "pylint-dev": "Pylint / PSF",
    "twisted": "Twisted Matrix Laboratories",
    "django": "Django Software Foundation",
    "numfocus": "NumFOCUS",
    "numpy": "NumFOCUS (NumPy)",
    "scipy": "NumFOCUS (SciPy)",
    "pandas-dev": "NumFOCUS (pandas)",
    "matplotlib": "NumFOCUS (Matplotlib)",
    "scikit-learn": "NumFOCUS (scikit-learn)",
    "scikit-image": "NumFOCUS (scikit-image)",
    "sympy": "SymPy / NumFOCUS",
    "networkx": "NetworkX / NumFOCUS",
    "astropy": "Astropy / NumFOCUS",
    "biopython": "Open Bioinformatics Foundation",
    "sunpy": "SunPy / OpenAstronomy",
    "openastronomy": "OpenAstronomy",
    "jupyter": "Project Jupyter / NumFOCUS",
    "jupyterlab": "Project Jupyter / NumFOCUS",
    "ipython": "Project Jupyter / NumFOCUS",
    "xarray": "NumFOCUS (xarray)",
    "dask": "NumFOCUS (Dask)",
    "zarr-developers": "NumFOCUS (Zarr)",
    "statsmodels": "NumFOCUS (Statsmodels)",

    # Web, Collaboration, Education & Social
    "zulip": "Zulip",
    "oppia": "Oppia Foundation",
    "freecodecamp": "freeCodeCamp",
    "metacall": "MetaCall",
    "matrix-org": "Matrix.org Foundation",
    "processing": "The Processing Foundation (p5.js)",
    "sugarlabs": "Sugar Labs",
    "openmrs": "OpenMRS",
    "fossasia": "FOSSASIA",

    # Foundations & Major Open Source Ecosystems
    "apache": "Apache Software Foundation",
    "mozilla": "Mozilla",
    "torproject": "The Tor Project",
    "owasp": "OWASP Foundation",
    "cern": "CERN / HSF",
    "root-project": "CERN (ROOT)",
    "eclipse": "Eclipse Foundation",
    "eclipse-theia": "Eclipse Foundation",
    "jenkins": "Jenkins",
    "jenkinsci": "Jenkins",
    "wikimedia": "Wikimedia Foundation",
    "gnome": "GNOME Foundation",
    "kde": "KDE",
    "llvm": "LLVM Compiler Infrastructure",
    "qemu": "QEMU",
    "ffmpeg": "FFmpeg",
    "videolan": "VideoLAN (VLC)",
    "blender": "Blender Foundation",
    "inkscape": "Inkscape",
    "godotengine": "Godot Engine",
    "wireshark": "Wireshark Foundation",
    "audacity": "Audacity",
    "mesonbuild": "The Meson Build System",
    "spdx": "Linux Foundation (SPDX)",
    "git": "Git",
    "gitlab-org": "GitLab",
    "neovim": "Neovim",
    "libreoffice": "The Document Foundation (LibreOffice)",
    "joplin": "Joplin",
    "checkstyle": "Checkstyle",
    "jabref": "JabRef",
    "openstreetmap": "OpenStreetMap",
    "libretro": "RetroArch / Libretro",
    "radareorg": "radare2",
    "musescore": "MuseScore",
    "mixxx": "Mixxx DJ Software",
    "scummvm": "ScummVM",
    "octave": "GNU Octave",
    "cloudfoundry": "Cloud Foundry",
    # AI / ML / MLOps Curated Organizations
    "ml4sci": "ML4SCI (Machine Learning for Science)",
    "mlpack": "mlpack (Machine Learning)",
    "kubeflow": "Kubeflow (CNCF MLOps)",
    "flyteorg": "Flyte (CNCF MLOps)",
    "deepchem": "DeepChem",
    "redhenlab": "Red Hen Lab",
    "kornia": "Kornia (Computer Vision)",
}

ALL_GSOC_OWNERS = set(GSOC_ORGS_MAP.keys())

# The 4 primary target organizations: NumFOCUS, Python Software Foundation, DeepChem, Kornia
FOCUS_GSOC_ORGS: Dict[str, str] = {
    # NumFOCUS
    "numfocus": "NumFOCUS",
    "numpy": "NumFOCUS (NumPy)",
    "scipy": "NumFOCUS (SciPy)",
    "pandas-dev": "NumFOCUS (pandas)",
    "matplotlib": "NumFOCUS (Matplotlib)",
    "scikit-learn": "NumFOCUS (scikit-learn)",
    "scikit-image": "NumFOCUS (scikit-image)",
    "sympy": "NumFOCUS (SymPy)",
    "networkx": "NumFOCUS (NetworkX)",
    "astropy": "NumFOCUS (Astropy)",
    "jupyter": "NumFOCUS (Project Jupyter)",
    "jupyterlab": "NumFOCUS (JupyterLab)",
    "dask": "NumFOCUS (Dask)",
    "xarray": "NumFOCUS (xarray)",
    "zarr-developers": "NumFOCUS (Zarr)",
    "statsmodels": "NumFOCUS (Statsmodels)",

    # Python Software Foundation
    "psf": "Python Software Foundation",
    "python": "Python Software Foundation",
    "pallets": "Python Software Foundation (Pallets)",
    "pypa": "Python Software Foundation (PyPA)",
    "celery": "Python Software Foundation (Celery)",
    "pylint-dev": "Python Software Foundation (Pylint)",

    # DeepChem
    "deepchem": "DeepChem",

    # Kornia
    "kornia": "Kornia",
}
FOCUS_GSOC_OWNERS = set(FOCUS_GSOC_ORGS.keys())

def is_focus_gsoc_org(owner: str, repo_name: str = "") -> bool:
    """Returns True if the owner matches one of the 5 curated AI/ML/MLOps organizations."""
    if not owner:
        return False
    owner_clean = owner.strip().lower()
    if owner_clean in FOCUS_GSOC_OWNERS:
        return True
    if repo_name and repo_name.strip().lower() in FOCUS_GSOC_OWNERS:
        return True
    return False

def get_gsoc_info(owner: str, repo_name: str = "") -> Optional[str]:
    """Returns the official GSoC organization name if owner or repo is in GSoC registry, else None."""
    if not owner:
        return None
    owner_clean = owner.strip().lower()
    if owner_clean in GSOC_ORGS_MAP:
        return GSOC_ORGS_MAP[owner_clean]
    
    if repo_name:
        repo_clean = repo_name.strip().lower()
        if repo_clean in GSOC_ORGS_MAP:
            return GSOC_ORGS_MAP[repo_clean]
            
    return None

def is_gsoc_org(owner: str, repo_name: str = "") -> bool:
    """Returns True if the owner or repo name matches any known GSoC organization."""
    return get_gsoc_info(owner, repo_name) is not None

