package plugin

import (
	"errors"
	"fmt"

	"github.com/grafana/grafana-plugin-sdk-go/backend"

	"github.com/intersystems-community/iris-ai-examples/connectors/grafana-iris-datasource/pkg/plugin/client"
)

// errorResponse turns an error from the IRIS client into a response Grafana can classify. The error
// source matters: Grafana counts "downstream" errors (the user's query, their credentials, their
// server) separately from "plugin" errors (faults in this code), and alerting treats them differently.
func errorResponse(err error) backend.DataResponse {
	status, source := classify(err)
	return backend.ErrDataResponseWithSource(status, source, fmt.Sprintf("iris: %v", trimPrefix(err)))
}

func classify(err error) (backend.Status, backend.ErrorSource) {
	var (
		sqlErr   *client.SQLError
		authErr  *client.AuthError
		unreach  *client.UnreachableError
		tooLarge *client.TooLargeError
	)
	switch {
	case errors.As(err, &sqlErr), errors.As(err, &tooLarge):
		return backend.StatusBadRequest, backend.ErrorSourceDownstream
	case errors.As(err, &authErr):
		if authErr.HTTPStatus == 403 {
			return backend.StatusForbidden, backend.ErrorSourceDownstream
		}
		return backend.StatusUnauthorized, backend.ErrorSourceDownstream
	case errors.As(err, &unreach):
		return backend.StatusBadGateway, backend.ErrorSourceDownstream
	default:
		return backend.StatusInternal, backend.ErrorSourcePlugin
	}
}

// trimPrefix drops the "iris: " the client puts on its messages, because errorResponse adds it once.
func trimPrefix(err error) string {
	msg := err.Error()
	const p = "iris: "
	if len(msg) >= len(p) && msg[:len(p)] == p {
		return msg[len(p):]
	}
	return msg
}
