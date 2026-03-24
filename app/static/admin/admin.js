(() => {
    const layout = document.querySelector("[data-admin-layout]");
    const overlay = document.querySelector("[data-admin-overlay]");
    const sidebarToggles = document.querySelectorAll("[data-admin-sidebar-toggle]");
    const flash = document.querySelector("[data-admin-flash]");

    const isMobileViewport = () => window.matchMedia("(max-width: 991px)").matches;

    const openSidebar = () => {
        if (!layout || !isMobileViewport()) {
            return;
        }

        layout.classList.add("sidebar-open");
    };

    const closeSidebar = () => {
        if (!layout) {
            return;
        }

        layout.classList.remove("sidebar-open");
    };

    sidebarToggles.forEach((toggle) => {
        toggle.addEventListener("click", () => {
            if (!layout || !isMobileViewport()) {
                return;
            }

            if (layout.classList.contains("sidebar-open")) {
                closeSidebar();
                return;
            }

            openSidebar();
        });
    });

    if (overlay) {
        overlay.addEventListener("click", closeSidebar);
    }

    window.addEventListener("resize", () => {
        if (!isMobileViewport()) {
            closeSidebar();
        }
    });

    window.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeSidebar();
        }
    });

    document.addEventListener("submit", (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) {
            return;
        }

        const confirmMessage = form.dataset.confirm;
        if (confirmMessage && !window.confirm(confirmMessage)) {
            event.preventDefault();
        }
    });

    if (flash) {
        window.setTimeout(() => {
            flash.classList.add("is-hidden");
            window.setTimeout(() => {
                flash.remove();
            }, 250);
        }, 4500);
    }
})();
