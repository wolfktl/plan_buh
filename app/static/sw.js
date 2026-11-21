/* Service Worker для браузерных push-уведомлений */
self.addEventListener("push", function (event) {
  var data = {};
  try { data = event.data.json(); } catch (e) { data = { title: "Напоминание", body: event.data ? event.data.text() : "" }; }
  var title = data.title || "Планировщик бухгалтера";
  var options = {
    body: data.body || "",
    tag: "planbuh-" + (data.date || Date.now()),
    icon: "/static/icon.png",
    badge: "/static/icon.png",
    data: { url: "/" }
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: "window" }).then(function (list) {
      for (var i = 0; i < list.length; i++) {
        if (list[i].url.indexOf(self.location.origin) === 0 && "focus" in list[i]) return list[i].focus();
      }
      if (clients.openWindow) return clients.openWindow("/");
    })
  );
});
